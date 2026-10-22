"""SQLAlchemy models. Importing this package registers every table on ``Base.metadata``."""

from app.models.scholarship import ImportRun, Scholarship, ScholarshipCriterion, ScholarshipValue

__all__ = ["ImportRun", "Scholarship", "ScholarshipCriterion", "ScholarshipValue"]
