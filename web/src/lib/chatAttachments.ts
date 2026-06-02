export const FILE_REF_MIME = "application/x-career-os-file-ref";

export type FileRefAttachment = {
  type: "file_ref";
  path: string;
  label?: string;
  optimization_level?: string;
};

export function displayAttachmentLabel(att: FileRefAttachment): string {
  if (att.label) return att.label;
  const parts = att.path.split("/");
  return parts[parts.length - 1] || att.path;
}

export function formatAttachmentsForMessage(
  attachments: FileRefAttachment[],
): string {
  if (attachments.length === 0) return "";
  const names = attachments.map((a) => displayAttachmentLabel(a)).join("、");
  return `\n\n[引用简历: ${names}]`;
}

export function parseFileRefFromDataTransfer(dt: DataTransfer): FileRefAttachment | null {
  const raw = dt.getData(FILE_REF_MIME);
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as FileRefAttachment;
    if (parsed?.type === "file_ref" && parsed.path) return parsed;
  } catch {
    return null;
  }
  return null;
}

export function fileRefFromOutputItem(item: {
  path: string;
  optimization_level?: string;
}): FileRefAttachment {
  const parts = item.path.split("/");
  return {
    type: "file_ref",
    path: item.path,
    label: parts[parts.length - 1] || item.path,
    optimization_level: item.optimization_level,
  };
}
