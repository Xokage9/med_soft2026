import enum


class StaffRole(str, enum.Enum):
    doctor = "doctor"
    laboratory_technician = "laboratory-technician"
    nurse = "nurse"
    other = "other"


class Sex(str, enum.Enum):
    male = "M"
    female = "F"
    unknown = "U"


STAFF_NAME_MIN, STAFF_NAME_MAX = 1, 24
STAFF_POSITION_MIN, STAFF_POSITION_MAX = 3, 24

DIAGNOSIS_CODE_LEN = 6
DIAGNOSIS_NAME_MIN, DIAGNOSIS_NAME_MAX = 3, 24

PATIENT_NAME_MIN, PATIENT_NAME_MAX = 1, 32
PATIENT_COMMENT_MAX = 32
PATIENT_MIN_BIRTH_YEAR = 1900

PRESCRIPTION_MIN, PRESCRIPTION_MAX = 3, 128

USERNAME_MIN, USERNAME_MAX = 3, 16
USERNAME_PATTERN = r"^[A-Za-z0-9._-]+$"
GENERATED_PASSWORD_LEN = 12

ADMIN_PASSWORD_MIN = 12
