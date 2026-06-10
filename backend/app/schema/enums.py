from enum import Enum


class LearningContentType(str, Enum):
    ARTICLE = "article"
    CODING_PROBLEM = "coding_problem"
    MULTIPLE_CHOICE = "multiple_choice"


class PracticeMode(str, Enum):
    CODING_PROBLEM = "coding_problem"
    MULTIPLE_CHOICE = "multiple_choice"
    EITHER = "either"


class ArticleDepth(str, Enum):
    LIGHT = "light"
    STANDARD = "standard"
    DEEP = "deep"


class ExampleStyle(str, Enum):
    MINIMAL = "minimal"
    BALANCED = "balanced"
    EXAMPLE_FIRST = "example_first"


class MemoryType(str, Enum):
    BACKGROUND = "background"
    ERROR_PATTERN = "error_pattern"
    HEURISTIC = "heuristic"
    MASTERY_SIGNAL = "mastery_signal"
    PREFERENCE_SIGNAL = "preference_signal"


class MemoryStatus(str, Enum):
    ACTIVE = "active"
    WATCH = "watch"
    RESOLVED = "resolved"


class AttemptCorrectness(str, Enum):
    CORRECT = "correct"
    PARTIALLY_CORRECT = "partially_correct"
    INCORRECT = "incorrect"
    RUNTIME_ERROR = "runtime_error"


class MasteryStatus(str, Enum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    PRACTICING = "practicing"
    MASTERED = "mastered"
    REGRESSED = "regressed"


class MemoryIntegrityAction(str, Enum):
    CREATE_NEW = "create_new"
    UPDATE_EXISTING = "update_existing"
    MERGE = "merge"
    SKIP_DUPLICATE = "skip_duplicate"
    KEEP_BOTH_SCOPED = "keep_both_scoped"
    FLAG_CONFLICT = "flag_conflict"


class HintLevel(str, Enum):
    NUDGE = "nudge"
    CONCEPTUAL = "conceptual"
    SPECIFIC = "specific"
    NEAR_SOLUTION = "near_solution"


class TeachingAction(str, Enum):
    NORMAL_HINT = "normal_hint"
    QUICK_RECAP = "quick_recap"
    CONTRAST_EXAMPLE = "contrast_example"
    QUICK_RECAP_THEN_HINT = "quick_recap_then_hint"


class MemoryRerankPurpose(str, Enum):
    HINT_GENERATION = "hint_generation"
    CODE_CORRECTION = "code_correction"
    CONTENT_GENERATION = "content_generation"
    ROADMAP_PLANNING = "roadmap_planning"
