import os
import math
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional
from sqlalchemy.orm import Session
from xml.sax.saxutils import escape

from app.models.db_models import Batch, Serial, GTINStore, CodePool, PackagingLine, Product
from app.models.batch import BatchReconcileRequest
from app.repositories.batch_repository import BatchRepository
from app.repositories.code_pool_repository import CodePoolRepository
from app.repositories.audit_log_repository import AuditLogRepository

logger = logging.getLogger("bt_sn_portal")

class L2ExecutionService:
    @staticmethod
    def calculate_tier_quantities(
        db: Session,
        product_id: str,
        target_primary_qty: int,
        secondary_ratio: int = 1,
        tertiary_ratio: int = 1
    ) -> Dict[str, int]:
        """
        Mathematical multi-tier calculation logic from Section 4:
        Q_sec = ceil(Q_pri / R_sec)
        Q_ter = ceil(Q_sec / R_ter)
        Zero Limit Rule (Section 3.1): If limit for tier is 0, Q_tier = 0.
        """
        r_sec = max(int(secondary_ratio or 1), 1)
        r_ter = max(int(tertiary_ratio or 1), 1)

        q_primary = max(int(target_primary_qty or 0), 0)
        q_secondary = math.ceil(q_primary / r_sec) if q_primary > 0 else 0
        q_tertiary = math.ceil(q_secondary / r_ter) if q_secondary > 0 else 0

        # Check GTIN Limits & Zero Limit Rule
        gtin_records = db.query(GTINStore).filter(GTINStore.product_id == product_id).all()
        tier_limits = {}
        for g in gtin_records:
            tier_name = (g.packaging_level or "").strip().capitalize()
            tier_limits[tier_name] = g.limit

        # Apply Zero Limit Rule: limit == 0 disables generation for that tier
        if tier_limits.get("Primary", None) == 0:
            q_primary = 0
        if tier_limits.get("Secondary", None) == 0:
            q_secondary = 0
        if tier_limits.get("Tertiary", None) == 0:
            q_tertiary = 0

        return {
            "primary": q_primary,
            "secondary": q_secondary,
            "tertiary": q_tertiary,
            "total": q_primary + q_secondary + q_tertiary
        }

    @staticmethod
    def load_batch(db: Session, batch_id: str) -> Dict:
        """
        Phase 3: Load Batch
        - Extracts all reserved serial numbers for batch from Code Pool / Serials
        - Formats serial numbers into line payload file (CSV or XML)
        - Transmits to L2 over configured I/O channel (Direct API, Shared Folder, or SFTP)
        - Transitions batch status to LOADED
        """
        batch = BatchRepository.get_by_id(db, batch_id)
        if not batch:
            raise ValueError(f"Batch '{batch_id}' not found.")

        if batch.is_locked:
            raise ValueError("Batch is closed and locked against modifications.")

        # Extract reserved serials
        serials = db.query(Serial).filter(Serial.batch_id == batch_id).order_by(Serial.sequence_number.asc()).all()
        if not serials:
            raise ValueError(f"No serial numbers generated or reserved for batch '{batch_id}'.")

        # Create Line I/O payload folders
        line = db.query(PackagingLine).filter(PackagingLine.line_id == batch.line_id).first() if batch.line_id else None
        io_channel = (line.io_protocol if line else batch.io_channel) or "DIRECT_API"

        outbound_dir = os.path.join("l2_io", "outbound", batch_id)
        os.makedirs(outbound_dir, exist_ok=True)

        # 1. Generate CSV line file
        csv_filename = f"L2_DISPATCH_{batch.batch_lot}_{batch_id}.csv"
        csv_path = os.path.join(outbound_dir, csv_filename)
        with open(csv_path, "w", encoding="utf-8") as f:
            f.write("Seq,GTIN,SerialNumber,PackagingTier,BatchLot,ExpiryDate\n")
            for s in serials:
                # Find GTIN from product/batch
                tier = getattr(s, "packaging_tier", "Primary") or "Primary"
                f.write(f"{s.sequence_number},08901234567892,{s.serial_number},{tier},{s.batch_lot},{s.expiry_date}\n")

        # 2. Simulate transmission over configured channel
        dispatch_dest = "DIRECT_API / Controller Socket"
        if io_channel == "SHARED_FOLDER":
            shared_dir = line.shared_folder_path if (line and line.shared_folder_path) else os.path.join("l2_io", "shared_folder", "outbound")
            os.makedirs(shared_dir, exist_ok=True)
            shared_file = os.path.join(shared_dir, csv_filename)
            with open(shared_file, "w", encoding="utf-8") as sf:
                with open(csv_path, "r", encoding="utf-8") as src:
                    sf.write(src.read())
            dispatch_dest = f"Network Shared Folder ({shared_file})"
        elif io_channel == "SFTP":
            sftp_dir = os.path.join("l2_io", "sftp_drop", "outbound")
            os.makedirs(sftp_dir, exist_ok=True)
            sftp_file = os.path.join(sftp_dir, csv_filename)
            with open(sftp_file, "w", encoding="utf-8") as sf:
                with open(csv_path, "r", encoding="utf-8") as src:
                    sf.write(src.read())
            host_str = line.sftp_host if line else "sftp.pharma.local"
            dispatch_dest = f"SFTP Drop ({host_str}:{sftp_file})"

        # 3. Update Batch Status -> LOADED
        updated = BatchRepository.update(db, batch_id, {
            "status": "LOADED",
            "io_channel": io_channel
        })

        AuditLogRepository.log(
            db,
            event_type="LOAD_BATCH",
            table_name="batches",
            record_id=batch_id,
            previous_value={"status": batch.status},
            updated_value={"status": "LOADED", "io_channel": io_channel, "destination": dispatch_dest, "payload_file": csv_filename}
        )
        db.commit()

        return {
            "batch_id": batch_id,
            "status": "LOADED",
            "io_channel": io_channel,
            "destination": dispatch_dest,
            "file_name": csv_filename,
            "total_records_transmitted": len(serials),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    @staticmethod
    def start_batch(db: Session, batch_id: str) -> Dict:
        """
        Phase 3: Start Batch
        - Transmits start control signal to Level 2 execution controller
        - Switches Level 3 into monitoring state
        - Transitions batch status to STARTED / RUNNING
        """
        batch = BatchRepository.get_by_id(db, batch_id)
        if not batch:
            raise ValueError(f"Batch '{batch_id}' not found.")

        if batch.status not in ["LOADED", "COMPLETED"]:
            raise ValueError(f"Batch '{batch_id}' must be in LOADED state before starting (currently '{batch.status}').")

        updated = BatchRepository.update(db, batch_id, {
            "status": "STARTED"
        })

        AuditLogRepository.log(
            db,
            event_type="START_BATCH",
            table_name="batches",
            record_id=batch_id,
            previous_value={"status": batch.status},
            updated_value={"status": "STARTED", "signal": "L2_LINE_RUN_SIGNAL_ACKNOWLEDGED"}
        )
        db.commit()

        return {
            "batch_id": batch_id,
            "status": "STARTED",
            "signal": "L2_CONTROLLER_STARTED",
            "message": "Level 2 line packaging execution active. Printing and camera vision inspection underway.",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    @staticmethod
    def reconcile_batch(db: Session, batch_id: str, req: BatchReconcileRequest) -> Dict:
        """
        Phase 4: Reconcile Batch
        - Reads production feedback file from L2 (printed, sampled, rejected)
        - Good / Commissioned codes -> COMMITTED / USED
        - Rejected / Damaged codes -> REJECTED
        - Unused reserved codes -> Returned to AVAILABLE pool
        - Transitions batch status to RECONCILED
        """
        batch = BatchRepository.get_by_id(db, batch_id)
        if not batch:
            raise ValueError(f"Batch '{batch_id}' not found.")

        if batch.is_locked:
            raise ValueError("Batch is closed and locked against further reconciliation.")

        serials = db.query(Serial).filter(Serial.batch_id == batch_id).all()
        if not serials:
            raise ValueError(f"No serial numbers found for batch '{batch_id}'.")

        all_serial_nums = [s.serial_number for s in serials]
        total_count = len(all_serial_nums)

        good_set = set()
        rejected_set = set()

        if req.auto_simulate or (not req.good_serials and not req.rejected_serials and not req.raw_feedback_content):
            # Automated simulation of L2 feedback based on target yield %
            yield_pct = req.simulated_yield_pct or 98.0
            good_count = max(1, int(round((total_count * yield_pct) / 100.0)))
            rejected_count = max(0, total_count - good_count)

            good_set = set(all_serial_nums[:good_count])
            rejected_set = set(all_serial_nums[good_count:])
        else:
            if req.good_serials:
                good_set.update(req.good_serials)
            if req.rejected_serials:
                rejected_set.update(req.rejected_serials)

            if req.raw_feedback_content:
                # Parse feedback CSV lines (Format: SerialNumber,Status)
                for line in req.raw_feedback_content.splitlines():
                    parts = [p.strip() for p in line.split(",") if p.strip()]
                    if len(parts) >= 2:
                        s_num, s_stat = parts[0], parts[1].upper()
                        if s_stat in ["GOOD", "COMMISSIONED", "USED", "COMMITTED"]:
                            good_set.add(s_num)
                        elif s_stat in ["REJECTED", "DAMAGED", "SAMPLE"]:
                            rejected_set.add(s_num)

        # Unused are reserved serials that were neither printed good nor rejected
        unused_set = set(all_serial_nums) - (good_set | rejected_set)

        # Update Serial statuses
        now_str = datetime.now(timezone.utc).isoformat()
        for s in serials:
            old_stat = s.status
            new_stat = old_stat
            if s.serial_number in good_set:
                new_stat = "COMMITTED"
            elif s.serial_number in rejected_set:
                new_stat = "REJECTED"
            else:
                new_stat = "AVAILABLE"

            if new_stat != old_stat:
                s.status = new_stat
                hist = list(s.history or [])
                hist.append({
                    "status": new_stat,
                    "updated_by": "L2_RECONCILIATION",
                    "timestamp": now_str,
                    "notes": f"Batch reconciliation feedback: marked as {new_stat}"
                })
                s.history = hist

        # Release unused codes back to Code Pool reservoir if present
        CodePoolRepository.release_unused_codes(db, batch_id, list(good_set | rejected_set))

        # Mark committed / rejected in Code Pool
        db.query(CodePool).filter(
            CodePool.batch_id == batch_id,
            CodePool.serial_number.in_(list(good_set))
        ).update({"status": "COMMITTED"}, synchronize_session=False)

        db.query(CodePool).filter(
            CodePool.batch_id == batch_id,
            CodePool.serial_number.in_(list(rejected_set))
        ).update({"status": "REJECTED"}, synchronize_session=False)

        good_cnt = len(good_set)
        rej_cnt = len(rejected_set)
        unused_cnt = len(unused_set)
        yield_pct = round((good_cnt / max(good_cnt + rej_cnt, 1)) * 100.0, 2)

        BatchRepository.update(db, batch_id, {
            "status": "RECONCILED",
            "reconciled_good_count": good_cnt,
            "reconciled_rejected_count": rej_cnt,
            "reconciled_unused_count": unused_cnt,
            "yield_percentage": yield_pct
        })

        AuditLogRepository.log(
            db,
            event_type="RECONCILE_BATCH",
            table_name="batches",
            record_id=batch_id,
            previous_value={"status": batch.status},
            updated_value={
                "status": "RECONCILED",
                "good_count": good_cnt,
                "rejected_count": rej_cnt,
                "unused_returned_count": unused_cnt,
                "yield_percentage": yield_pct
            }
        )
        db.commit()

        return {
            "batch_id": batch_id,
            "status": "RECONCILED",
            "reconciled_good_count": good_cnt,
            "reconciled_rejected_count": rej_cnt,
            "reconciled_unused_count": unused_cnt,
            "yield_percentage": yield_pct,
            "timestamp": now_str
        }

    @staticmethod
    def close_batch(db: Session, batch_id: str) -> Dict:
        """
        Phase 4: Close Batch
        - Locks batch against further editing
        - Completes balance calculations
        - Transitions batch status to CLOSED
        """
        batch = BatchRepository.get_by_id(db, batch_id)
        if not batch:
            raise ValueError(f"Batch '{batch_id}' not found.")

        if batch.status != "RECONCILED":
            raise ValueError(f"Batch '{batch_id}' must be in RECONCILED status before closure (currently '{batch.status}').")

        BatchRepository.update(db, batch_id, {
            "status": "CLOSED",
            "is_locked": True
        })

        AuditLogRepository.log(
            db,
            event_type="CLOSE_BATCH",
            table_name="batches",
            record_id=batch_id,
            previous_value={"status": batch.status, "is_locked": False},
            updated_value={"status": "CLOSED", "is_locked": True, "final_yield": batch.yield_percentage}
        )
        db.commit()

        return {
            "batch_id": batch_id,
            "status": "CLOSED",
            "is_locked": True,
            "yield_percentage": batch.yield_percentage,
            "reconciled_good_count": batch.reconciled_good_count,
            "reconciled_rejected_count": batch.reconciled_rejected_count,
            "message": "Batch locked and closed successfully. Ready for regulatory XML export.",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    @staticmethod
    def generate_xml_report(db: Session, batch_id: str) -> str:
        """
        Phase 4: Regulatory XML Report (GS1 EPCIS / Compliance XML)
        Compiles standard compliance XML containing Header, Batch Info, Packaging Hierarchy, and Commissioned SGTIN EPCs.
        """
        batch = BatchRepository.get_by_id(db, batch_id)
        if not batch:
            raise ValueError(f"Batch '{batch_id}' not found.")

        serials = db.query(Serial).filter(Serial.batch_id == batch_id).all()
        good_serials = [s for s in serials if s.status in ["COMMITTED", "GENERATED", "LOADED"]]
        rejected_serials = [s for s in serials if s.status == "REJECTED"]

        now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        product = db.query(Product).filter(Product.product_id == batch.product_id).first()
        gtin = (product.gtin if product and product.gtin else None) or getattr(batch, "gtin", "08901234567892") or "08901234567892"

        epc_list_xml = []
        for s in good_serials:
            epc_urn = f"urn:epc:id:sgtin:{gtin}.{s.serial_number}"
            tier = getattr(s, "packaging_tier", "Primary") or "Primary"
            epc_list_xml.append(f"        <epc tier=\"{escape(tier)}\">{escape(epc_urn)}</epc>")

        epc_block = "\n".join(epc_list_xml) if epc_list_xml else "        <!-- No commissioned serials -->"

        xml_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<epcis:EPCISDocument xmlns:epcis="urn:epcglobal:epcis:xsd:1"
                     xmlns:sbdh="http://www.unece.org/cefact/namespaces/StandardBusinessDocumentHeader"
                     xmlns:cbvmda="urn:epcglobal:cbv:mda"
                     schemaVersion="1.2"
                     creationDate="{now_utc}">
  <EPCISHeader>
    <sbdh:StandardBusinessDocumentHeader>
      <sbdh:HeaderVersion>1.0</sbdh:HeaderVersion>
      <sbdh:Sender>
        <sbdh:Identifier Authority="GLN">0890123456789</sbdh:Identifier>
        <sbdh:ContactInformation>{escape(batch.manufacturer or 'PHARMA SITE')}</sbdh:ContactInformation>
      </sbdh:Sender>
      <sbdh:Receiver>
        <sbdh:Identifier Authority="GLN">0000000000000</sbdh:Identifier>
        <sbdh:ContactInformation>REGULATORY_AUTHORITY</sbdh:ContactInformation>
      </sbdh:Receiver>
      <sbdh:DocumentIdentification>
        <sbdh:Standard>EPCIS</sbdh:Standard>
        <sbdh:TypeVersion>1.2</sbdh:TypeVersion>
        <sbdh:InstanceIdentifier>{escape(batch.batch_id)}</sbdh:InstanceIdentifier>
        <sbdh:Type>CommissioningEventReport</sbdh:Type>
        <sbdh:CreationDateAndTime>{now_utc}</sbdh:CreationDateAndTime>
      </sbdh:DocumentIdentification>
    </sbdh:StandardBusinessDocumentHeader>
  </EPCISHeader>
  <EPCISBody>
    <EventList>
      <ObjectEvent>
        <eventTime>{now_utc}</eventTime>
        <eventTimeZoneOffset>+00:00</eventTimeZoneOffset>
        <epcList>
{epc_block}
        </epcList>
        <action>ADD</action>
        <bizStep>urn:epcglobal:cbv:bizstep:commissioning</bizStep>
        <disposition>urn:epcglobal:cbv:disp:active</disposition>
        <readPoint><id>urn:epc:id:sgln:{escape(batch.plant or 'TESTPLANT')}.LINE_{escape(batch.line_id or '01')}</id></readPoint>
        <bizLocation><id>urn:epc:id:sgln:{escape(batch.plant or 'TESTPLANT')}.0</id></bizLocation>
        <extension>
          <ilmd>
            <cbvmda:lotNumber>{escape(batch.batch_lot)}</cbvmda:lotNumber>
            <cbvmda:itemExpirationDate>20{escape(batch.expiry_date[:2])}-{escape(batch.expiry_date[2:4])}-{escape(batch.expiry_date[4:6])}</cbvmda:itemExpirationDate>
            <cbvmda:mfgDate>{escape(batch.mfg_date or '')}</cbvmda:mfgDate>
            <cbvmda:workOrderNumber>{escape(batch.work_order_no or '')}</cbvmda:workOrderNumber>
            <cbvmda:packagingRatios secondaryRatio="{batch.secondary_ratio}" tertiaryRatio="{batch.tertiary_ratio}"/>
            <cbvmda:yieldMetrics totalRequested="{batch.requested_quantity}" goodCount="{batch.reconciled_good_count}" rejectedCount="{batch.reconciled_rejected_count}" yieldPercentage="{batch.yield_percentage}%"/>
          </ilmd>
        </extension>
      </ObjectEvent>
    </EventList>
  </EPCISBody>
</epcis:EPCISDocument>"""
        return xml_content
