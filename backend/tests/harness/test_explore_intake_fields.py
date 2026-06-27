from career_os.harness.explore_intake_fields import (
    extract_fields_from_resume,
    merge_intake_field_values,
)


def test_extract_fields_from_resume():
    """验证 extract fields from resume 场景。"""
    resume = """
    张三
    5年工作经验
    当前薪资：30k
    期望岗位：后端工程师
    期望薪资：40万
    """
    extracted = extract_fields_from_resume(resume)
    assert extracted["years_of_experience"] == "5年"
    assert extracted["current_salary"] == "30K"
    assert extracted["target_role"] == "后端工程师"
    assert extracted["target_salary"] == "40万"


def test_merge_prefers_user_values_over_extraction():
    """验证 merge prefers user values over extraction 场景。"""
    resume = "期望岗位：后端工程师\n3年工作经验"
    resolved, extracted, pending = merge_intake_field_values(
        resume_text=resume,
        user_values={
            "years_of_experience": "6年",
            "current_salary": "",
            "target_salary": "",
            "target_role": "",
        },
    )
    assert resolved["years_of_experience"] == "6年"
    assert resolved["target_role"] == "后端工程师"
    assert "current_salary" in pending
    assert "target_salary" in pending


def test_merge_pending_when_missing_everywhere():
    """验证 merge pending when missing everywhere 场景。"""
    resolved, _, pending = merge_intake_field_values(
        resume_text="只有项目经历描述，没有结构化字段",
        user_values={
            "years_of_experience": "",
            "current_salary": "",
            "target_salary": "",
            "target_role": "",
        },
    )
    assert resolved["years_of_experience"] == ""
    assert set(pending) == {
        "years_of_experience",
        "current_salary",
        "target_salary",
        "target_role",
    }
