export default function() {
  function keydown(event) {
    if (event.repeat || event.isComposing) return;
    const editor = document.querySelector('.st-key-question_input textarea');
    if (!editor) return;
    const target = event.target;
    const editable = target.closest?.('input,textarea,select,[contenteditable="true"],[role="textbox"],[role="combobox"]');
    if (event.key === '/' && !editable && !event.ctrlKey && !event.metaKey && !event.altKey) {
      event.preventDefault(); editor.focus();
    }
    if (event.key === 'Enter' && (event.ctrlKey || event.metaKey) && target === editor) {
      const button = document.querySelector('.st-key-query_send button');
      if (button && !button.disabled && editor.value.trim()) { event.preventDefault(); button.click(); }
    }
  }
  document.addEventListener('keydown', keydown);
  return () => document.removeEventListener('keydown', keydown);
}
