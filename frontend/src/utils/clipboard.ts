export async function copyText(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    // Continue with the compatibility path below.
  }

  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.readOnly = true;
  textarea.dataset.copyFallback = "true";
  textarea.style.position = "fixed";
  textarea.style.inset = "-9999px auto auto -9999px";
  document.body.append(textarea);

  try {
    textarea.select();
    return (
      typeof document.execCommand === "function" && document.execCommand("copy")
    );
  } catch {
    return false;
  } finally {
    textarea.remove();
  }
}
