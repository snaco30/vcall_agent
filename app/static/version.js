async function loadAppVersionBadge(buttonId = "appVersionBtn", summaryId = "appVersionSummary") {
    const btn = document.getElementById(buttonId);
    if (!btn) return;
    try {
        const res = await fetch("/api/version");
        if (!res.ok) return;
        const data = await res.json();
        btn.textContent = data.version || "V1.0.002";
        btn.title = data.summary || "업데이트 내역 보기";
        const summaryEl = document.getElementById(summaryId);
        if (summaryEl && data.summary) {
            summaryEl.textContent = data.summary;
        }
        window.__appVersionInfo = data;
    } catch {
        btn.textContent = "V1.0.002";
    }
}

function renderVersionChangelog(containerEl, changelog) {
    if (!containerEl) return;
    containerEl.innerHTML = (changelog || [])
        .map(
            (entry) => `
            <section class="space-y-2">
                <div class="flex items-baseline justify-between gap-2">
                    <h4 class="text-sm font-bold text-zinc-900">${entry.version}</h4>
                    <span class="text-[11px] text-zinc-500">${entry.date || ""}</span>
                </div>
                ${entry.summary ? `<p class="text-xs text-indigo-700 font-medium">${entry.summary}</p>` : ""}
                <ul class="text-xs text-zinc-600 space-y-1 list-disc pl-4">
                    ${(entry.items || []).map((item) => `<li>${item}</li>`).join("")}
                </ul>
            </section>
        `,
        )
        .join("");
}

function openVersionModal() {
    const modal = document.getElementById("versionModal");
    const listEl = document.getElementById("versionChangelogList");
    const titleEl = document.getElementById("versionModalTitle");
    const data = window.__appVersionInfo;
    if (titleEl) {
        titleEl.textContent = data?.version ? `${data.version} 업데이트` : "버전 정보";
    }
    if (listEl) {
        renderVersionChangelog(listEl, data?.changelog || []);
    }
    modal?.classList.remove("hidden");
    document.body.classList.add("overflow-hidden");
}

function closeVersionModal() {
    document.getElementById("versionModal")?.classList.add("hidden");
    document.body.classList.remove("overflow-hidden");
}

function bindVersionModal() {
    document.getElementById("appVersionBtn")?.addEventListener("click", openVersionModal);
    document.getElementById("versionModalCloseBtn")?.addEventListener("click", closeVersionModal);
    document.getElementById("versionModal")?.addEventListener("click", (event) => {
        if (event.target.id === "versionModal") closeVersionModal();
    });
    window.addEventListener("keydown", (event) => {
        if (event.key !== "Escape") return;
        if (!document.getElementById("versionModal")?.classList.contains("hidden")) {
            closeVersionModal();
        }
    });
}
