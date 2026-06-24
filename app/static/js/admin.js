(() => {
  const formatFileSummary = (files) => {
    if (!files.length) {
      return "Nenhum arquivo selecionado.";
    }
    if (files.length === 1) {
      return `Selecionado: ${files[0].name}`;
    }
    const names = files.slice(0, 3).map((file) => file.name);
    const extra = files.length > names.length ? ` +${files.length - names.length}` : "";
    return `${files.length} arquivos selecionados: ${names.join(", ")}${extra}`;
  };

  const renderPreview = async (files, previewEl) => {
    if (!previewEl) return;
    previewEl.textContent = "";
    if (!files.length) return;

    const imageFiles = files.filter((file) => file.type && file.type.startsWith("image/")).slice(0, 4);
    if (!imageFiles.length) {
      const text = document.createElement("span");
      text.className = "upload-preview-note";
      text.textContent = "Arquivo pronto para envio.";
      previewEl.appendChild(text);
      return;
    }

    await Promise.all(
      imageFiles.map(
        (file) =>
          new Promise((resolve) => {
            const reader = new FileReader();
            reader.onload = () => {
              const item = document.createElement("div");
              item.className = "upload-thumb";
              const img = document.createElement("img");
              img.alt = file.name;
              img.src = reader.result;
              item.appendChild(img);
              previewEl.appendChild(item);
              resolve();
            };
            reader.onerror = () => resolve();
            reader.readAsDataURL(file);
          })
      )
    );
  };

  const bindUploadField = (field) => {
    const input = field.querySelector('input[type="file"]');
    const feedback = field.querySelector("[data-upload-feedback]");
    const preview = field.querySelector("[data-upload-preview]");
    if (!input || (!feedback && !preview)) return;

    const defaultText = feedback?.textContent?.trim() || "Nenhum arquivo selecionado.";

    const sync = async () => {
      const files = Array.from(input.files || []);
      field.classList.toggle("has-files", files.length > 0);
      if (feedback) {
        feedback.textContent = files.length ? formatFileSummary(files) : defaultText;
        feedback.classList.toggle("is-active", files.length > 0);
      }
      await renderPreview(files, preview);
    };

    input.addEventListener("change", sync);
    sync();
  };

  document.querySelectorAll(".upload-field").forEach(bindUploadField);
})();
