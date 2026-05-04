import enum

class EPipelineStage(str, enum.Enum):
    EXTRACTION = "extraction"
    NORMALIZATION = "normalization"
    AI_TASK = "ai_task"
    EMBEDDING = "embedding"
    PERSISTENCE = "persistence"
