from datetime import datetime, timezone
from typing import Dict, List, Optional
from sqlalchemy.orm import Session

from app.models.db_models import Role, RolePermission, User, UserPermissionOverride
from app.repositories.audit_log_repository import AuditLogRepository

AVAILABLE_MODULES = {
    "dashboard": {
        "name": "Dashboard",
        "description": "System health, KPIs, and operational overview.",
        "actions": ["view"]
    },
    "products": {
        "name": "Product Management",
        "description": "Master formulations, NDC-10/11, and master product records.",
        "actions": ["view", "create", "edit"]
    },
    "gtin_store": {
        "name": "GTIN Store & Tiers",
        "description": "Multi-tier GTIN store, packaging levels, and case quantity limits.",
        "actions": ["view", "create", "edit"]
    },
    "lines": {
        "name": "Packaging Lines",
        "description": "Shop-floor lines, direct API, shared folders, and SFTP endpoints.",
        "actions": ["view", "create", "edit", "test_io"]
    },
    "code_pool": {
        "name": "Code Pool Reservoir",
        "description": "Pre-allocated SGTIN/serial import and pool stats.",
        "actions": ["view", "import"]
    },
    "batches": {
        "name": "Batch Serialization",
        "description": "Work orders, multi-tier ratios, execution, reconciliation, and locking.",
        "actions": ["view", "create", "edit", "execute", "reconcile", "close_lock", "export_xml"]
    },
    "sgtin": {
        "name": "SGTIN CSV Utility",
        "description": "High-volume CSPRNG barcode generation and streaming CSV export.",
        "actions": ["view", "generate", "export_csv"]
    },
    "verification": {
        "name": "In-Line Scanner Verification",
        "description": "2D DataMatrix barcode lookup and lifecycle status transitions.",
        "actions": ["view", "verify", "transition_status"]
    },
    "reports": {
        "name": "Reports & Yield Analytics",
        "description": "Batch summaries, packaging yields, and regulatory report exports.",
        "actions": ["view", "export"]
    },
    "audit_logs": {
        "name": "Audit Trail (21 CFR Part 11)",
        "description": "Forensic, immutable change logs and before/after inspection.",
        "actions": ["view"]
    },
    "user_management": {
        "name": "User Management",
        "description": "Admin-controlled user accounts, deactivation, and password resets.",
        "actions": ["view", "create", "edit", "deactivate", "reset_password"]
    },
    "roles": {
        "name": "Roles & Privileges",
        "description": "Definition of roles and granular permission matrices.",
        "actions": ["view", "create", "edit", "delete"]
    }
}

STANDARD_ROLE_TEMPLATES = {
    "System Administrator": {
        "description": "Full administrative control over user accounts, roles, security, and all plant modules.",
        "is_system_role": True,
        "permissions": {
            "dashboard": ["view"],
            "products": ["view", "create", "edit"],
            "gtin_store": ["view", "create", "edit"],
            "lines": ["view", "create", "edit", "test_io"],
            "code_pool": ["view", "import"],
            "batches": ["view", "create", "edit", "execute", "reconcile", "close_lock", "export_xml"],
            "sgtin": ["view", "generate", "export_csv"],
            "verification": ["view", "verify", "transition_status"],
            "reports": ["view", "export"],
            "audit_logs": ["view"],
            "user_management": ["view", "create", "edit", "deactivate", "reset_password"],
            "roles": ["view", "create", "edit", "delete"]
        }
    },
    "Serialization Operator": {
        "description": "Shop-floor operational workflows: batch initiation, serial generation, packaging line reconciliation.",
        "is_system_role": True,
        "permissions": {
            "dashboard": ["view"],
            "lines": ["view", "test_io"],
            "code_pool": ["view", "import"],
            "batches": ["view", "create", "edit", "execute", "reconcile"],
            "sgtin": ["view", "generate", "export_csv"],
            "verification": ["view", "verify", "transition_status"]
        }
    },
    "Quality / Compliance Reviewer": {
        "description": "Quality assurance and release: inspect records, approve/lock batches, review audit logs, and export reports.",
        "is_system_role": True,
        "permissions": {
            "dashboard": ["view"],
            "products": ["view"],
            "gtin_store": ["view"],
            "lines": ["view"],
            "batches": ["view", "close_lock", "export_xml"],
            "reports": ["view", "export"],
            "audit_logs": ["view"],
            "verification": ["view", "verify"]
        }
    },
    "Read-Only Auditor": {
        "description": "Strict view-only inspection access across pharmaceutical records and compliance audit trail.",
        "is_system_role": True,
        "permissions": {
            "dashboard": ["view"],
            "products": ["view"],
            "gtin_store": ["view"],
            "lines": ["view"],
            "batches": ["view"],
            "reports": ["view"],
            "audit_logs": ["view"],
            "verification": ["view"]
        }
    }
}


class RBACService:
    @classmethod
    def seed_default_roles(cls, db: Session):
        now_str = datetime.now(timezone.utc).isoformat()
        for role_name, config in STANDARD_ROLE_TEMPLATES.items():
            role = db.query(Role).filter(Role.role_name == role_name).first()
            if not role:
                role = Role(
                    role_name=role_name,
                    description=config["description"],
                    is_system_role=config["is_system_role"],
                    created_at=now_str
                )
                db.add(role)
                db.commit()
                db.refresh(role)

                # Seed permissions
                for mod, actions in config["permissions"].items():
                    for act in actions:
                        perm = RolePermission(
                            role_id=role.id,
                            module_key=mod,
                            action_key=act,
                            is_allowed=True
                        )
                        db.add(perm)
                db.commit()

    @classmethod
    def get_role_permissions_map(cls, db: Session, role_id: int) -> Dict[str, List[str]]:
        perms = db.query(RolePermission).filter(
            RolePermission.role_id == role_id,
            RolePermission.is_allowed == True
        ).all()
        res: Dict[str, List[str]] = {}
        for p in perms:
            if p.module_key not in res:
                res[p.module_key] = []
            res[p.module_key].append(p.action_key)
        return res

    @classmethod
    def get_user_effective_permissions(cls, db: Session, user: User) -> Dict[str, List[str]]:
        """
        Calculates effective permissions:
        1. Base permissions from user's assigned role.
        2. Applies user-specific overrides (explicit grant or explicit denial).
        Default policy is default-deny.
        """
        if not user.is_active:
            return {}

        effective: Dict[str, set] = {}

        # 1. Base from role
        if user.role_id:
            role_perms = db.query(RolePermission).filter(
                RolePermission.role_id == user.role_id,
                RolePermission.is_allowed == True
            ).all()
            for rp in role_perms:
                if rp.module_key not in effective:
                    effective[rp.module_key] = set()
                effective[rp.module_key].add(rp.action_key)
        else:
            # Fallback legacy lookup by role string if role_id not linked yet
            legacy_role = db.query(Role).filter(Role.role_name == user.role).first()
            if legacy_role:
                user.role_id = legacy_role.id
                db.commit()
                return cls.get_user_effective_permissions(db, user)

        # 2. User-level overrides
        overrides = db.query(UserPermissionOverride).filter(
            UserPermissionOverride.user_id == user.id
        ).all()
        for ov in overrides:
            if ov.module_key not in effective:
                effective[ov.module_key] = set()
            if ov.is_allowed:
                effective[ov.module_key].add(ov.action_key)
            else:
                effective[ov.module_key].discard(ov.action_key)

        return {mod: sorted(list(acts)) for mod, acts in effective.items() if acts}

    @classmethod
    def has_permission(cls, db: Session, user: User, module_key: str, action_key: str) -> bool:
        if not user or not user.is_active:
            return False

        # 1. Check user override first
        user_override = db.query(UserPermissionOverride).filter(
            UserPermissionOverride.user_id == user.id,
            UserPermissionOverride.module_key == module_key,
            UserPermissionOverride.action_key == action_key
        ).first()

        if user_override is not None:
            return user_override.is_allowed

        # 2. Check role permissions
        role_id = user.role_id
        if not role_id and user.role:
            r = db.query(Role).filter(Role.role_name == user.role).first()
            if r:
                role_id = r.id

        if not role_id:
            return False

        perm = db.query(RolePermission).filter(
            RolePermission.role_id == role_id,
            RolePermission.module_key == module_key,
            RolePermission.action_key == action_key,
            RolePermission.is_allowed == True
        ).first()

        return perm is not None

    @classmethod
    def list_roles(cls, db: Session) -> List[Dict]:
        cls.seed_default_roles(db)
        roles = db.query(Role).order_by(Role.id.asc()).all()
        result = []
        for r in roles:
            perms_map = cls.get_role_permissions_map(db, r.id)
            result.append({
                "id": r.id,
                "role_name": r.role_name,
                "description": r.description or "",
                "is_system_role": r.is_system_role,
                "created_at": r.created_at,
                "permissions": perms_map
            })
        return result

    @classmethod
    def create_role(
        cls,
        db: Session,
        role_name: str,
        description: str,
        permissions: Dict[str, List[str]],
        actor: str = "admin"
    ) -> Role:
        clean_name = role_name.strip()
        existing = db.query(Role).filter(Role.role_name.ilike(clean_name)).first()
        if existing:
            raise ValueError(f"Role '{clean_name}' already exists.")

        now_str = datetime.now(timezone.utc).isoformat()
        role = Role(
            role_name=clean_name,
            description=description.strip() if description else "",
            is_system_role=False,
            created_at=now_str
        )
        db.add(role)
        db.commit()
        db.refresh(role)

        for mod, actions in permissions.items():
            if mod in AVAILABLE_MODULES:
                for act in actions:
                    if act in AVAILABLE_MODULES[mod]["actions"]:
                        perm = RolePermission(
                            role_id=role.id,
                            module_key=mod,
                            action_key=act,
                            is_allowed=True
                        )
                        db.add(perm)
        db.commit()

        AuditLogRepository.log(
            db=db,
            event_type="ROLE_CREATED",
            table_name="roles",
            record_id=str(role.id),
            previous_value=None,
            updated_value={"role_name": role.role_name, "description": role.description, "permissions": permissions},
            performed_by=actor
        )
        db.commit()
        return role

    @classmethod
    def update_role(
        cls,
        db: Session,
        role_id: int,
        description: Optional[str] = None,
        permissions: Optional[Dict[str, List[str]]] = None,
        actor: str = "admin"
    ) -> Role:
        role = db.query(Role).filter(Role.id == role_id).first()
        if not role:
            raise ValueError(f"Role ID {role_id} not found.")

        old_perms = cls.get_role_permissions_map(db, role.id)
        old_desc = role.description

        if description is not None:
            role.description = description.strip()

        if permissions is not None:
            # Clear existing role permissions
            db.query(RolePermission).filter(RolePermission.role_id == role.id).delete()
            for mod, actions in permissions.items():
                if mod in AVAILABLE_MODULES:
                    for act in actions:
                        if act in AVAILABLE_MODULES[mod]["actions"]:
                            perm = RolePermission(
                                role_id=role.id,
                                module_key=mod,
                                action_key=act,
                                is_allowed=True
                            )
                            db.add(perm)

        db.commit()
        db.refresh(role)

        AuditLogRepository.log(
            db=db,
            event_type="ROLE_PERMISSIONS_UPDATED",
            table_name="roles",
            record_id=str(role.id),
            previous_value={"description": old_desc, "permissions": old_perms},
            updated_value={"role_name": role.role_name, "description": role.description, "permissions": permissions},
            performed_by=actor
        )
        db.commit()
        return role

    @classmethod
    def delete_role(cls, db: Session, role_id: int, actor: str = "admin") -> bool:
        role = db.query(Role).filter(Role.id == role_id).first()
        if not role:
            raise ValueError(f"Role ID {role_id} not found.")
        if role.is_system_role:
            raise ValueError(f"Cannot delete system role '{role.role_name}'. System roles are protected under 21 CFR Part 11.")

        # Check if users are assigned
        users_assigned = db.query(User).filter(User.role_id == role.id).count()
        if users_assigned > 0:
            raise ValueError(f"Cannot delete role '{role.role_name}': {users_assigned} user(s) are currently assigned to this role.")

        role_name = role.role_name
        db.query(RolePermission).filter(RolePermission.role_id == role.id).delete()
        db.delete(role)
        db.commit()

        AuditLogRepository.log(
            db=db,
            event_type="ROLE_DELETED",
            table_name="roles",
            record_id=str(role_id),
            previous_value={"role_name": role_name},
            updated_value=None,
            performed_by=actor
        )
        db.commit()
        return True

    @classmethod
    def set_user_override(
        cls,
        db: Session,
        user_id: int,
        module_key: str,
        action_key: str,
        is_allowed: bool,
        actor: str = "admin"
    ):
        if module_key not in AVAILABLE_MODULES:
            raise ValueError(f"Invalid module '{module_key}'.")
        if action_key not in AVAILABLE_MODULES[module_key]["actions"]:
            raise ValueError(f"Invalid action '{action_key}' for module '{module_key}'.")

        override = db.query(UserPermissionOverride).filter(
            UserPermissionOverride.user_id == user_id,
            UserPermissionOverride.module_key == module_key,
            UserPermissionOverride.action_key == action_key
        ).first()

        prev_status = override.is_allowed if override else None
        if override:
            override.is_allowed = is_allowed
        else:
            override = UserPermissionOverride(
                user_id=user_id,
                module_key=module_key,
                action_key=action_key,
                is_allowed=is_allowed
            )
            db.add(override)
        db.commit()

        AuditLogRepository.log(
            db=db,
            event_type="USER_PERMISSION_OVERRIDE",
            table_name="user_permission_overrides",
            record_id=f"user_{user_id}_{module_key}_{action_key}",
            previous_value={"is_allowed": prev_status},
            updated_value={"user_id": user_id, "module": module_key, "action": action_key, "is_allowed": is_allowed},
            performed_by=actor
        )
        db.commit()
