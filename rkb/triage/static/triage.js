const postDecision = async (hash, path, decision) => {
  const params = new URLSearchParams();
  params.set("path", path);
  params.set("decision", decision);

  const response = await fetch(`/pdf/${hash}/decide`, {
    method: "POST",
    body: params,
  });

  if (!response.ok) {
    const payload = await response.json();
    throw new Error(payload.error || "Decision request failed");
  }
  return response.json();
};

const fetchPages = async (hash, path) => {
  const response = await fetch(`/pdf/${hash}/pages?path=${encodeURIComponent(path)}`);
  if (!response.ok) {
    const payload = await response.json();
    throw new Error(payload.error || "Page request failed");
  }
  return response.json();
};

document.addEventListener("click", async (event) => {
  const button = event.target.closest("button");
  if (!button) {
    return;
  }

  if (button.classList.contains("decide-btn")) {
    const hash = button.dataset.hash;
    const path = button.dataset.path;
    const decision = button.dataset.decision;
    try {
      const payload = await postDecision(hash, path, decision);
      const marker = document.querySelector(`[data-decision-for="${hash}"]`);
      if (marker) {
        marker.textContent = `Decision: ${payload.decision}`;
        marker.classList.remove("approved", "rejected", "undecided");
        marker.classList.add(payload.decision);
      }
    } catch (error) {
      window.alert(error.message);
    }
  }

  if (button.classList.contains("pages-btn")) {
    const hash = button.dataset.hash;
    const path = button.dataset.path;
    const preview = document.getElementById(`preview-${hash}`);
    if (!preview) {
      return;
    }
    try {
      const payload = await fetchPages(hash, path);
      preview.innerHTML = "";
      payload.pages.forEach((encoded, index) => {
        const image = document.createElement("img");
        image.alt = `Page ${index + 1}`;
        image.src = `data:image/png;base64,${encoded}`;
        preview.appendChild(image);
      });
    } catch (error) {
      window.alert(error.message);
    }
  }
});

