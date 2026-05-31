export type ExploreIntakePayload = {
  resume_text: string;
  years_of_experience: string;
  current_salary: string;
  target_salary: string;
  target_role: string;
};

export const emptyExploreIntake = (): ExploreIntakePayload => ({
  resume_text: "",
  years_of_experience: "",
  current_salary: "",
  target_salary: "",
  target_role: "",
});

export async function submitExploreIntake(payload: ExploreIntakePayload): Promise<void> {
  const response = await fetch("/v1/profile/explore-intake", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error("提交失败");
  }
}
