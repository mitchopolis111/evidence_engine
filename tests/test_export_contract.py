def generate_evidence_zip(source_dir):
    """
    Backward-compatibility wrapper expected by router and tests.
    Delegates to the canonical export implementation without changing behavior.
    """
    return zip_folder(source_dir)