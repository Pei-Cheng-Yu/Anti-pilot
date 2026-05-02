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
