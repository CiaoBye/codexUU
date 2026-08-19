export function formatModelLabel(modelId: string): string {
  const raw = modelId.trim();
  if (!raw || raw === 'unknown') {
    return '未知模型';
  }

  const cleaned = raw
    .replace(/_/g, '-')
    .replace(/-thinking$/i, '')
    .replace(/-(low|high|preview|exp)$/i, '');

  const title = (part: string) =>
    /^\d/.test(part) ? part : part.charAt(0).toUpperCase() + part.slice(1).toLowerCase();

  if (/^gemini-/i.test(cleaned)) {
    return `Gemini ${cleaned.slice(7).split('-').map(title).join(' ')}`;
  }
  if (/^claude-/i.test(cleaned)) {
    const rest = cleaned.slice(7).replace(/(\d+)-(\d+)/g, '$1.$2');
    return `Claude ${rest.split('-').map(title).join(' ')}`;
  }
  if (/^gpt-/i.test(cleaned)) {
    return `GPT ${cleaned.slice(4).split('-').map(title).join(' ')}`;
  }
  return cleaned.split('-').map(title).join(' ');
}
