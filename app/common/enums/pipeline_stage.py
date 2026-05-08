import enum


class EPipelineStage(enum.StrEnum):
    EXTRACTION = "extraction"
    NORMALIZATION = "normalization"
    AI_TASK = "ai_task"
    EMBEDDING = "embedding"
    PERSISTENCE = "persistence"
