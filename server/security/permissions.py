import enum

from ..rules import StaffRole


class Perm(str, enum.Enum):
    ADMIN = "admin"
    DIAGNOSIS_READ = "diagnosis:read"
    PATIENT_READ = "patient:read"
    PATIENT_WRITE = "patient:write"
    EMR_READ = "emr:read"
    EMR_CREATE = "emr:create"
    EMR_WRITE = "emr:write"


ADMIN_ROLE = "admin"

_READ = {Perm.DIAGNOSIS_READ, Perm.PATIENT_READ, Perm.EMR_READ}

ROLE_PERMISSIONS: dict[str, frozenset[Perm]] = {
    ADMIN_ROLE: frozenset({Perm.ADMIN, Perm.DIAGNOSIS_READ}),
    StaffRole.doctor.value: frozenset(_READ | {Perm.PATIENT_WRITE, Perm.EMR_CREATE, Perm.EMR_WRITE}),
    StaffRole.nurse.value: frozenset(_READ | {Perm.PATIENT_WRITE, Perm.EMR_CREATE}),
    StaffRole.laboratory_technician.value: frozenset(_READ),
    StaffRole.other.value: frozenset(_READ),
}


def permissions_for(role: str) -> frozenset[Perm]:
    return ROLE_PERMISSIONS.get(role, frozenset())
