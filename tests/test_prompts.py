from trend_scout import prompts


def test_writer_and_judge_require_the_same_numbered_heading_format():
    required = "## <N>. <title>"
    assert required in prompts.WRITER_SYSTEM
    assert required in prompts.JUDGE_SYSTEM
