"""Small domain constants shared by the generator, ingestion, API and UI."""

DOC_TYPE_LABEL = {
    "8d": "8D Problem-Solving Report",
    "lessons_learned": "Lessons Learned Report",
    "field_failure": "Field Failure Analysis",
    "test_report": "Test Report",
    "dfmea": "Design FMEA",
    "pfmea": "Process FMEA",
    "dvpr": "DVP&R",
    "design_review": "Design Review Minutes",
    "ecn": "Engineering Change Notice",
    "supplier_quality": "Supplier Quality Report",
    "work_instruction": "Work Instruction",
    "drawing": "Engineering Drawing",
    "inspection_record": "Incoming Inspection Record",
    "recall": "Public Recall Record",
    "other": "Document",
}

# Role -> document classifications it may read (feature N; demo role switcher).
ROLE_ACCESS = {
    "new_engineer": ["public", "internal"],
    "engineer": ["public", "internal", "confidential"],
    "quality_sme": ["public", "internal", "confidential", "restricted"],
    "admin": ["public", "internal", "confidential", "restricted"],
}
DEFAULT_ROLE = "admin"
