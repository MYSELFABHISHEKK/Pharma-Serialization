from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy.orm import Session
from app.models.db_models import PackagingLine
from app.models.line import PackagingLineCreate
from app.repositories.audit_log_repository import AuditLogRepository

class LineRepository:
    @staticmethod
    def get_by_id(db: Session, line_id: str) -> Optional[PackagingLine]:
        line = db.query(PackagingLine).filter(PackagingLine.line_id == line_id).first()
        if not line and db.query(PackagingLine).count() == 0:
            LineRepository.list_all(db)
            line = db.query(PackagingLine).filter(PackagingLine.line_id == line_id).first()
        return line

    @staticmethod
    def list_all(db: Session) -> List[PackagingLine]:
        lines = db.query(PackagingLine).filter(PackagingLine.is_active == True).all()
        if not lines:
            default_lines = [
                PackagingLine(
                    line_id="LINE-01",
                    name="Blister Line 1",
                    plant="TESTPLANT",
                    io_protocol="DIRECT_API",
                    api_endpoint="http://127.0.0.1:8000/api/v1/l2/mock-controller/line-01",
                    shared_folder_path="l2_io/shared_folder/line_01",
                    sftp_host="sftp.pharma.local",
                    sftp_port=22,
                    sftp_user="line01_op",
                    sftp_drop_folder="/var/drop/line_01/outbound",
                    sftp_inbound_folder="/var/drop/line_01/inbound",
                    is_active=True,
                    created_at="2026-01-01T00:00:00Z"
                ),
                PackagingLine(
                    line_id="LINE-02",
                    name="Bottle Line 2",
                    plant="TESTPLANT",
                    io_protocol="SHARED_FOLDER",
                    shared_folder_path="l2_io/shared_folder/line_02",
                    sftp_host="sftp.pharma.local",
                    sftp_port=22,
                    sftp_user="line02_op",
                    sftp_drop_folder="/var/drop/line_02/outbound",
                    sftp_inbound_folder="/var/drop/line_02/inbound",
                    is_active=True,
                    created_at="2026-01-01T00:00:00Z"
                ),
                PackagingLine(
                    line_id="LINE-03",
                    name="Packaging Line 01",
                    plant="TESTPLANT_DGFT",
                    io_protocol="SFTP",
                    shared_folder_path="l2_io/shared_folder/line_03",
                    sftp_host="sftp.pharma.local",
                    sftp_port=22,
                    sftp_user="line03_op",
                    sftp_drop_folder="/var/drop/line_03/outbound",
                    sftp_inbound_folder="/var/drop/line_03/inbound",
                    is_active=True,
                    created_at="2026-01-01T00:00:00Z"
                )
            ]
            db.add_all(default_lines)
            db.commit()
            lines = db.query(PackagingLine).filter(PackagingLine.is_active == True).all()
        return lines

    @staticmethod
    def serialize_line(line: PackagingLine) -> dict:
        return {
            "line_id": line.line_id,
            "name": line.name,
            "plant": line.plant,
            "io_protocol": line.io_protocol,
            "shared_folder_path": line.shared_folder_path,
            "sftp_host": line.sftp_host,
            "sftp_port": line.sftp_port,
            "sftp_user": line.sftp_user,
            "sftp_password": line.sftp_password,
            "sftp_drop_folder": line.sftp_drop_folder,
            "sftp_inbound_folder": line.sftp_inbound_folder,
            "api_endpoint": line.api_endpoint,
            "is_active": line.is_active,
            "created_at": line.created_at
        }

    @staticmethod
    def create(db: Session, line: PackagingLineCreate) -> PackagingLine:
        db_line = PackagingLine(
            line_id=line.line_id,
            name=line.name,
            plant=line.plant,
            io_protocol=line.io_protocol or "DIRECT_API",
            shared_folder_path=line.shared_folder_path,
            sftp_host=line.sftp_host,
            sftp_port=line.sftp_port or 22,
            sftp_user=line.sftp_user,
            sftp_password=line.sftp_password,
            sftp_drop_folder=line.sftp_drop_folder,
            sftp_inbound_folder=line.sftp_inbound_folder,
            api_endpoint=line.api_endpoint,
            is_active=line.is_active,
            created_at=datetime.now(timezone.utc).isoformat()
        )
        db.add(db_line)
        db.commit()
        db.refresh(db_line)

        AuditLogRepository.log(
            db,
            event_type="CREATE_LINE",
            table_name="packaging_lines",
            record_id=db_line.line_id,
            previous_value=None,
            updated_value=LineRepository.serialize_line(db_line)
        )
        db.commit()
        return db_line

    @staticmethod
    def update(db: Session, line_id: str, update_data: dict) -> Optional[PackagingLine]:
        db_line = LineRepository.get_by_id(db, line_id)
        if not db_line:
            return None

        previous_data = LineRepository.serialize_line(db_line)

        for key, value in update_data.items():
            if hasattr(db_line, key) and value is not None:
                setattr(db_line, key, value)

        db.commit()
        db.refresh(db_line)

        AuditLogRepository.log(
            db,
            event_type="UPDATE_LINE",
            table_name="packaging_lines",
            record_id=db_line.line_id,
            previous_value=previous_data,
            updated_value=LineRepository.serialize_line(db_line)
        )
        db.commit()
        return db_line

