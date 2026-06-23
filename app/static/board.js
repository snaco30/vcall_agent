let authToken = "";
let currentUsername = "";
let boards = [];
let currentBoardId = null;
let currentPage = 1;
let currentQuery = "";
let editor = null;
let editingPostId = null;
let detailPostId = null;
let viewerInstance = null;
let selectedEditorImage = null;
let selectedEditorImageSrc = "";
let imageControlOverlay = null;
let imageAlignToolbar = null;
let imageResizeState = null;
let editorImageScrollHandler = null;
let editorImageWindowResizeHandler = null;
let editorImageOutsideClickHandler = null;

const PAGE_SIZE = 20;

const boardListEl = document.getElementById("boardList");
const currentBoardTitleEl = document.getElementById("currentBoardTitle");
const currentBoardMetaEl = document.getElementById("currentBoardMeta");
const postListEl = document.getElementById("postList");
const postPaginationEl = document.getElementById("postPagination");
const postSearchInputEl = document.getElementById("postSearchInput");
const postCreateBtnEl = document.getElementById("postCreateBtn");
const postExcelBtnEl = document.getElementById("postExcelBtn");
const excelImportModalEl = document.getElementById("excelImportModal");
const excelImportBoardLabelEl = document.getElementById("excelImportBoardLabel");
const excelTemplateDownloadBtnEl = document.getElementById("excelTemplateDownloadBtn");
const excelSelectedFileNameEl = document.getElementById("excelSelectedFileName");
const postExcelInputEl = document.getElementById("postExcelInput");
const excelValidationErrorsEl = document.getElementById("excelValidationErrors");
const excelImportResultMsgEl = document.getElementById("excelImportResultMsg");
const excelSaveBtnEl = document.getElementById("excelSaveBtn");
let pendingExcelFile = null;
let excelImportValidated = false;

const boardModalEl = document.getElementById("boardModal");
const boardFormEl = document.getElementById("boardForm");
const boardDeleteBtnEl = document.getElementById("boardDeleteBtn");

const postModalEl = document.getElementById("postModal");
const postModalTitleEl = document.getElementById("postModalTitle");
const postTitleInputEl = document.getElementById("postTitleInput");
const postPinnedInputEl = document.getElementById("postPinnedInput");
const attachmentInputEl = document.getElementById("attachmentInput");
const attachmentListEl = document.getElementById("attachmentList");
const postDeleteBtnEl = document.getElementById("postDeleteBtn");
const editorRootEl = document.getElementById("editorRoot");

const detailModalEl = document.getElementById("postDetailModal");
const detailTitleEl = document.getElementById("detailTitle");
const detailMetaEl = document.getElementById("detailMeta");
const detailViewerEl = document.getElementById("detailViewer");
const detailAttachmentsEl = document.getElementById("detailAttachments");
const commentListEl = document.getElementById("commentList");
const commentInputEl = document.getElementById("commentInput");
const commentSubmitBtnEl = document.getElementById("commentSubmitBtn");
const postModalBodyEl = document.getElementById("postModalBody");
const detailScrollAreaEl = document.getElementById("detailScrollArea");
const backupModalEl = document.getElementById("backupModal");
const backupStatusBoxEl = document.getElementById("backupStatusBox");
const backupResultMsgEl = document.getElementById("backupResultMsg");
const restoreFileInputEl = document.getElementById("restoreFileInput");
const restoreModeSelectEl = document.getElementById("restoreModeSelect");

function escapeHtml(value) {
    return (value ?? "")
        .toString()
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

function secureFetch(url, options = {}) {
    return fetch(url, {
        ...options,
        headers: {
            ...(options.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
            ...(options.headers || {}),
            Authorization: `Bearer ${authToken}`,
        },
    }).then(async (res) => {
        const data = await res.json().catch(() => ({}));
        if (res.status === 401) {
            alert("인증 세션이 만료되었습니다. 다시 로그인해 주세요.");
            location.href = "/";
            throw new Error("인증 만료");
        }
        if (!res.ok) {
            const detail = typeof data?.detail === "string" ? data.detail : `요청 실패 (${res.status})`;
            throw new Error(detail);
        }
        return data;
    });
}

function formatDateTime(value) {
    if (!value) return "-";
    return value.replace("T", " ").slice(0, 16);
}

function lockBodyScroll() {
    document.body.classList.add("overflow-hidden");
}

function unlockBodyScroll() {
    if (
        !postModalEl.classList.contains("hidden") ||
        !detailModalEl.classList.contains("hidden") ||
        !excelImportModalEl.classList.contains("hidden")
    ) {
        return;
    }
    document.body.classList.remove("overflow-hidden");
}

function resetScrollArea(el) {
    if (el) el.scrollTop = 0;
}

function getEditorWwContentEl() {
    return editorRootEl.querySelector(".toastui-editor-contents");
}

function findEditorImageBySrc(src) {
    if (!src) return null;
    const ww = getEditorWwContentEl();
    if (!ww) return null;
    return Array.from(ww.querySelectorAll("img")).find((img) => img.getAttribute("src") === src) || null;
}

function syncEditorHtmlFromDom() {
    const ww = getEditorWwContentEl();
    if (!ww || !editor) return;
    editor.setHTML(ww.innerHTML);
    if (selectedEditorImageSrc) {
        const img = findEditorImageBySrc(selectedEditorImageSrc);
        if (img) {
            selectEditorImage(img, false);
            return;
        }
    }
    deselectEditorImage();
}

function applyImageDimensions(img, widthPx) {
    const width = Math.max(50, Math.round(widthPx));
    img.style.width = `${width}px`;
    img.style.height = "auto";
    img.setAttribute("width", String(width));
    img.removeAttribute("height");
}

function getImageAlignment(img) {
    const block = img.closest("p, div");
    if (!block) return "left";
    const align = (block.style.textAlign || "").toLowerCase();
    if (align === "center" || align === "right") return align;
    return "left";
}

function setImageAlignment(img, align) {
    const ww = getEditorWwContentEl();
    let block = img.closest("p, div");
    if (!block || block === ww) {
        block = document.createElement("p");
        img.replaceWith(block);
        block.appendChild(img);
    }
    block.style.textAlign = align === "left" ? "" : align;
    if (!block.style.textAlign) {
        block.removeAttribute("style");
    }
    syncEditorHtmlFromDom();
    updateAlignToolbarState(align);
}

function updateAlignToolbarState(align) {
    if (!imageAlignToolbar) return;
    imageAlignToolbar.querySelectorAll("button[data-align]").forEach((btn) => {
        btn.classList.toggle("active", btn.dataset.align === align);
    });
}

function updateImageControlOverlay() {
    if (!selectedEditorImage || !imageControlOverlay || !imageAlignToolbar) return;
    const rect = selectedEditorImage.getBoundingClientRect();
    if (!rect.width) {
        deselectEditorImage();
        return;
    }
    imageControlOverlay.classList.remove("hidden");
    imageAlignToolbar.classList.remove("hidden");
    imageControlOverlay.style.left = `${rect.left}px`;
    imageControlOverlay.style.top = `${rect.top}px`;
    imageControlOverlay.style.width = `${rect.width}px`;
    imageControlOverlay.style.height = `${rect.height}px`;
    const toolbarTop = Math.max(8, rect.top - 40);
    imageAlignToolbar.style.left = `${rect.left}px`;
    imageAlignToolbar.style.top = `${toolbarTop}px`;
    updateAlignToolbarState(getImageAlignment(selectedEditorImage));
}

function deselectEditorImage() {
    selectedEditorImage = null;
    selectedEditorImageSrc = "";
    imageControlOverlay?.classList.add("hidden");
    imageAlignToolbar?.classList.add("hidden");
}

function selectEditorImage(img, scrollIntoView = false) {
    if (!img || img.tagName !== "IMG") return;
    selectedEditorImage = img;
    selectedEditorImageSrc = img.getAttribute("src") || "";
    updateImageControlOverlay();
    if (scrollIntoView) {
        img.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }
}

function onImageResizeMove(event) {
    if (!imageResizeState) return;
    const { img, handle, startX, startY, startWidth, startHeight, aspect } = imageResizeState;
    const dx = event.clientX - startX;
    const dy = event.clientY - startY;
    let newWidth = startWidth;
    let newHeight = startHeight;

    if (handle === "e" || handle === "se" || handle === "ne") {
        newWidth = startWidth + dx;
    } else if (handle === "w" || handle === "sw" || handle === "nw") {
        newWidth = startWidth - dx;
    }
    if (handle === "s" || handle === "se" || handle === "sw") {
        newHeight = startHeight + dy;
    } else if (handle === "n" || handle === "ne" || handle === "nw") {
        newHeight = startHeight - dy;
    }

    if (handle === "e" || handle === "w") {
        applyImageDimensions(img, newWidth);
    } else if (handle === "n" || handle === "s") {
        applyImageDimensions(img, newHeight * aspect);
    } else {
        applyImageDimensions(img, Math.max(newWidth, newHeight * aspect));
    }
    updateImageControlOverlay();
}

function onImageResizeEnd() {
    if (!imageResizeState) return;
    imageResizeState = null;
    document.removeEventListener("mousemove", onImageResizeMove);
    document.removeEventListener("mouseup", onImageResizeEnd);
    syncEditorHtmlFromDom();
}

function startImageResize(event, handle) {
    if (!selectedEditorImage) return;
    event.preventDefault();
    event.stopPropagation();
    const rect = selectedEditorImage.getBoundingClientRect();
    imageResizeState = {
        img: selectedEditorImage,
        handle,
        startX: event.clientX,
        startY: event.clientY,
        startWidth: rect.width,
        startHeight: rect.height,
        aspect: rect.width / Math.max(rect.height, 1),
    };
    document.addEventListener("mousemove", onImageResizeMove);
    document.addEventListener("mouseup", onImageResizeEnd);
}

function teardownEditorImageControls() {
    deselectEditorImage();
    onImageResizeEnd();
    if (editorImageScrollHandler) {
        postModalBodyEl?.removeEventListener("scroll", editorImageScrollHandler);
        editorImageScrollHandler = null;
    }
    if (editorImageWindowResizeHandler) {
        window.removeEventListener("resize", editorImageWindowResizeHandler);
        editorImageWindowResizeHandler = null;
    }
    if (editorImageOutsideClickHandler) {
        document.removeEventListener("mousedown", editorImageOutsideClickHandler);
        editorImageOutsideClickHandler = null;
    }
    imageControlOverlay?.remove();
    imageAlignToolbar?.remove();
    imageControlOverlay = null;
    imageAlignToolbar = null;
}

function setupEditorImageControls() {
    teardownEditorImageControls();

    imageControlOverlay = document.createElement("div");
    imageControlOverlay.className = "board-editor-img-overlay hidden";
    imageControlOverlay.innerHTML = `
        <span class="board-editor-img-handle nw" data-handle="nw"></span>
        <span class="board-editor-img-handle ne" data-handle="ne"></span>
        <span class="board-editor-img-handle sw" data-handle="sw"></span>
        <span class="board-editor-img-handle se" data-handle="se"></span>
        <span class="board-editor-img-handle n" data-handle="n"></span>
        <span class="board-editor-img-handle s" data-handle="s"></span>
        <span class="board-editor-img-handle e" data-handle="e"></span>
        <span class="board-editor-img-handle w" data-handle="w"></span>
    `;
    document.body.appendChild(imageControlOverlay);

    imageAlignToolbar = document.createElement("div");
    imageAlignToolbar.className = "board-editor-img-align hidden";
    imageAlignToolbar.innerHTML = `
        <button type="button" data-align="left">왼쪽</button>
        <button type="button" data-align="center">가운데</button>
        <button type="button" data-align="right">오른쪽</button>
    `;
    document.body.appendChild(imageAlignToolbar);

    imageControlOverlay.querySelectorAll(".board-editor-img-handle").forEach((handleEl) => {
        handleEl.addEventListener("mousedown", (event) => {
            startImageResize(event, handleEl.dataset.handle);
        });
    });

    imageAlignToolbar.querySelectorAll("button[data-align]").forEach((btn) => {
        btn.addEventListener("mousedown", (event) => event.preventDefault());
        btn.addEventListener("click", (event) => {
            event.preventDefault();
            event.stopPropagation();
            if (!selectedEditorImage) return;
            setImageAlignment(selectedEditorImage, btn.dataset.align);
        });
    });

    const ww = getEditorWwContentEl();
    if (!ww) return;

    ww.addEventListener("click", (event) => {
        if (event.target.tagName === "IMG") {
            event.preventDefault();
            event.stopPropagation();
            selectEditorImage(event.target);
            return;
        }
        if (
            !imageControlOverlay.contains(event.target) &&
            !imageAlignToolbar.contains(event.target)
        ) {
            deselectEditorImage();
        }
    });

    editorImageScrollHandler = () => updateImageControlOverlay();
    editorImageWindowResizeHandler = () => updateImageControlOverlay();
    postModalBodyEl?.addEventListener("scroll", editorImageScrollHandler, { passive: true });
    window.addEventListener("resize", editorImageWindowResizeHandler, { passive: true });

    editorImageOutsideClickHandler = (event) => {
        if (!selectedEditorImage) return;
        const inEditor = editorRootEl.contains(event.target);
        const inControls =
            imageControlOverlay.contains(event.target) || imageAlignToolbar.contains(event.target);
        if (!inEditor && !inControls) {
            deselectEditorImage();
        }
    };
    document.addEventListener("mousedown", editorImageOutsideClickHandler);
}

async function uploadInlineImage(blob) {
    const form = new FormData();
    form.append("file", blob);
    return secureFetch(`/api/boards/posts/${editingPostId}/inline-images`, {
        method: "POST",
        body: form,
    });
}

function initEditor(initialHtml = "") {
    editorRootEl.innerHTML = "";
    editor = new toastui.Editor({
        el: editorRootEl,
        height: "460px",
        initialEditType: "wysiwyg",
        previewStyle: "vertical",
        initialValue: initialHtml,
        hooks: {
            addImageBlobHook: async (blob, callback) => {
                if (!editingPostId) return;
                try {
                    const result = await uploadInlineImage(blob);
                    const imageUrl = `${result.url}?token=${encodeURIComponent(authToken)}`;
                    callback(imageUrl, blob.name || "inline-image");
                    window.setTimeout(() => {
                        const ww = getEditorWwContentEl();
                        const imgs = ww?.querySelectorAll("img");
                        const img = imgs?.[imgs.length - 1];
                        if (img) selectEditorImage(img);
                    }, 80);
                } catch (error) {
                    alert(error.message || "이미지 업로드에 실패했습니다.");
                }
            },
        },
    });
    window.setTimeout(setupEditorImageControls, 0);
}

function renderBoardList() {
    if (!boards.length) {
        boardListEl.innerHTML = `<p class="text-xs text-zinc-500 px-2 py-3">등록된 게시판이 없습니다.</p>`;
        return;
    }
    boardListEl.innerHTML = boards
        .map((board) => {
            const activeClass = board.id === currentBoardId ? "ring-indigo-300 bg-indigo-50/70" : "ring-zinc-200 hover:bg-zinc-50";
            const inactiveLabel = board.is_active ? "" : `<span class="text-[9px] text-rose-600 shrink-0">OFF</span>`;
            const newPostDot =
                (board.new_post_count || 0) > 0
                    ? `<span class="w-1.5 h-1.5 rounded-full bg-rose-500 shrink-0" title="최근 15일 이내 새 글 ${board.new_post_count}건"></span>`
                    : "";
            return `
                <div class="board-card rounded-lg ring-1 ${activeClass} px-2 py-1.5 cursor-pointer transition-colors" data-board-id="${board.id}" role="button" tabindex="0">
                    <div class="flex items-center gap-1 min-w-0">
                        <span class="text-[11px] shrink-0">${escapeHtml(board.icon || "📋")}</span>
                        <span class="text-[11px] font-semibold text-zinc-900 truncate">${escapeHtml(board.name)}</span>
                        <span class="ml-auto shrink-0 flex items-center gap-1">
                            ${newPostDot}
                            <span class="text-[10px] text-indigo-600">${board.post_count || 0}</span>
                        </span>
                        ${inactiveLabel}
                    </div>
                    ${board.description ? `<p class="text-[10px] text-zinc-400 truncate mt-0.5 pl-4 pointer-events-none">${escapeHtml(board.description)}</p>` : ""}
                    <div class="mt-1 flex justify-end">
                        <button type="button" data-board-edit-id="${board.id}" class="board-edit-btn text-[10px] px-1.5 py-0.5 rounded bg-zinc-100 text-zinc-500 hover:bg-zinc-200">설정</button>
                    </div>
                </div>
            `;
        })
        .join("");
}

function selectBoard(boardId) {
    currentBoardId = Number(boardId);
    currentPage = 1;
    currentQuery = "";
    postSearchInputEl.value = "";
    renderBoardList();
    loadPosts(1).catch((error) => alert(error.message));
}

async function loadBoards() {
    boards = await secureFetch("/api/boards");
    if (!currentBoardId && boards.length) {
        const firstActive = boards.find((board) => board.is_active) || boards[0];
        currentBoardId = firstActive.id;
    }
    renderBoardList();
    if (currentBoardId) {
        await loadPosts();
    } else {
        currentBoardTitleEl.textContent = "게시판을 생성해 주세요";
        currentBoardMetaEl.textContent = "";
        postCreateBtnEl.classList.add("hidden");
        postExcelBtnEl.classList.add("hidden");
    }
}

function currentBoard() {
    return boards.find((board) => board.id === currentBoardId) || null;
}

function setExcelSaveEnabled(enabled) {
    excelImportValidated = enabled;
    excelSaveBtnEl.disabled = !enabled;
}

function renderExcelValidationErrors(errors) {
    if (!errors?.length) {
        excelValidationErrorsEl.classList.add("hidden");
        excelValidationErrorsEl.innerHTML = "";
        return;
    }
    excelValidationErrorsEl.classList.remove("hidden");
    excelValidationErrorsEl.innerHTML = errors
        .slice(0, 10)
        .map((item) => `<p>${item.row}행: ${escapeHtml(item.message)}</p>`)
        .join("");
}

async function validatePostExcel(file) {
    const board = currentBoard();
    if (!board || !file) return;
    if (!file.name.toLowerCase().endsWith(".xlsx")) {
        throw new Error("엑셀 파일(.xlsx)만 업로드할 수 있습니다.");
    }
    const form = new FormData();
    form.append("file", file);
    const res = await fetch(`/api/boards/${board.id}/posts/import/validate`, {
        method: "POST",
        headers: { Authorization: `Bearer ${authToken}` },
        body: form,
    });
    const data = await res.json().catch(() => ({}));
    if (res.status === 401) {
        alert("인증 세션이 만료되었습니다.");
        location.href = "/";
        return;
    }
    if (!res.ok) {
        throw new Error(data.detail || "검증 요청 실패");
    }
    renderExcelValidationErrors(data.errors);
    showExcelImportResult(data.message || "", !data.valid);
    setExcelSaveEnabled(Boolean(data.valid));
    return data;
}

async function uploadPostExcel(file) {
    const board = currentBoard();
    if (!board || !file) return;
    if (!file.name.toLowerCase().endsWith(".xlsx")) {
        throw new Error("엑셀 파일(.xlsx)만 업로드할 수 있습니다.");
    }
    const form = new FormData();
    form.append("file", file);
    const res = await fetch(`/api/boards/${board.id}/posts/import`, {
        method: "POST",
        headers: { Authorization: `Bearer ${authToken}` },
        body: form,
    });
    const data = await res.json().catch(() => ({}));
    if (res.status === 401) {
        alert("인증 세션이 만료되었습니다.");
        location.href = "/";
        return;
    }
    if (!res.ok) {
        throw new Error(data.detail || "엑셀 업로드 실패");
    }
    const errSuffix = data.errors?.length ? ` · 실패 ${data.failed}건` : "";
    showExcelImportResult(`저장 완료: 성공 ${data.imported}건${errSuffix}`, (data.failed || 0) > 0);
    if (data.imported > 0 && (data.failed || 0) === 0) {
        window.setTimeout(() => closeExcelImportModal(), 1500);
    }
    currentPage = 1;
    currentQuery = "";
    postSearchInputEl.value = "";
    await loadBoards();
    await loadPosts(1);
    return data;
}

function showExcelImportResult(message, isError = false) {
    excelImportResultMsgEl.textContent = message;
    excelImportResultMsgEl.classList.remove("hidden", "bg-emerald-50", "text-emerald-800", "bg-rose-50", "text-rose-800");
    excelImportResultMsgEl.classList.add(isError ? "bg-rose-50" : "bg-emerald-50", isError ? "text-rose-800" : "text-emerald-800");
}

function resetExcelImportModal() {
    pendingExcelFile = null;
    excelImportValidated = false;
    postExcelInputEl.value = "";
    excelSelectedFileNameEl.textContent = "선택된 파일 없음";
    excelImportResultMsgEl.classList.add("hidden");
    renderExcelValidationErrors([]);
    setExcelSaveEnabled(false);
    excelSaveBtnEl.textContent = "저장하기";
}

function openExcelImportModal() {
    const board = currentBoard();
    if (!board) return;
    resetExcelImportModal();
    excelImportBoardLabelEl.textContent = `대상 게시판: ${board.name}`;
    excelImportModalEl.classList.remove("hidden");
    lockBodyScroll();
}

function closeExcelImportModal() {
    excelImportModalEl.classList.add("hidden");
    resetExcelImportModal();
    unlockBodyScroll();
}

async function downloadPostExcelTemplate() {
    const board = currentBoard();
    if (!board) return;
    const res = await fetch(`/api/boards/${board.id}/posts/import-template`, {
        headers: { Authorization: `Bearer ${authToken}` },
    });
    if (res.status === 401) {
        alert("인증 세션이 만료되었습니다.");
        location.href = "/";
        return;
    }
    if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || "양식 다운로드 실패");
    }
    const blob = await res.blob();
    const cd = res.headers.get("Content-Disposition") || "";
    const match = cd.match(/filename=\"?([^\";]+)\"?/);
    const filename = match ? match[1] : "board_posts_import_template.xlsx";
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
}

async function loadPosts(page = currentPage) {
    const board = currentBoard();
    if (!board) return;
    currentPage = page;
    currentBoardTitleEl.textContent = board.name;
    currentBoardMetaEl.textContent = `${board.slug} · ${board.description || "설명 없음"}`;
    postCreateBtnEl.classList.remove("hidden");
    postExcelBtnEl.classList.remove("hidden");

    const query = new URLSearchParams({
        page: String(currentPage),
        page_size: String(PAGE_SIZE),
    });
    if (currentQuery.trim()) query.set("q", currentQuery.trim());
    const result = await secureFetch(`/api/boards/${board.id}/posts?${query.toString()}`);

    if (!result.items.length) {
        postListEl.innerHTML = `<div class="bg-white rounded-xl ring-1 ring-zinc-200 p-8 text-center text-sm text-zinc-500">게시글이 없습니다.</div>`;
    } else {
        postListEl.innerHTML = result.items
            .map(
                (post) => `
                <article class="bg-white rounded-xl ring-1 ring-zinc-200 shadow-sm p-4">
                    <div class="flex items-start justify-between gap-3">
                        <div class="min-w-0">
                            <button class="post-detail-btn text-left" data-post-id="${post.id}">
                                <h3 class="text-base font-bold text-zinc-900 break-words">${post.is_pinned ? "📌 " : ""}${escapeHtml(post.title || "(제목 없음)")}</h3>
                                <p class="text-xs text-zinc-500 mt-1">작성자 ${escapeHtml(post.author_username)} · ${formatDateTime(post.created_at)} · 조회 ${post.view_count}</p>
                            </button>
                        </div>
                        <button class="post-edit-btn text-[11px] px-2 py-1 rounded bg-zinc-100 text-zinc-600 hover:bg-zinc-200" data-post-id="${post.id}">수정</button>
                    </div>
                </article>
            `
            )
            .join("");
    }
    renderPagination(result.total, result.page, result.page_size);
}

function renderPagination(total, page, pageSize) {
    const totalPages = Math.max(1, Math.ceil(total / pageSize));
    const start = total === 0 ? 0 : (page - 1) * pageSize + 1;
    const end = Math.min(page * pageSize, total);

    if (totalPages <= 1) {
        postPaginationEl.classList.add("hidden");
        postPaginationEl.innerHTML = total
            ? `<p class="text-xs text-zinc-500 w-full text-center">총 ${total}건</p>`
            : "";
        return;
    }

    postPaginationEl.classList.remove("hidden");
    const pages = buildPageNumbers(page, totalPages);
    const pageButtons = pages
        .map((item) => {
            if (item === "...") {
                return `<span class="px-1 text-xs text-zinc-400">…</span>`;
            }
            const active = item === page;
            return `<button data-page="${item}" class="page-btn min-w-[2rem] px-2 py-1.5 rounded-lg text-xs font-medium ${
                active ? "bg-indigo-600 text-white" : "bg-zinc-100 text-zinc-700 hover:bg-zinc-200"
            }">${item}</button>`;
        })
        .join("");

    postPaginationEl.innerHTML = `
        <p class="text-xs text-zinc-500">${start}-${end} / 총 ${total}건 · 페이지당 ${pageSize}개</p>
        <div class="flex flex-wrap items-center justify-center gap-1">
            <button data-page="1" class="page-btn px-2 py-1.5 rounded-lg text-xs bg-zinc-100 text-zinc-700 hover:bg-zinc-200" ${page === 1 ? "disabled" : ""}>«</button>
            <button data-page="${Math.max(1, page - 1)}" class="page-btn px-2 py-1.5 rounded-lg text-xs bg-zinc-100 text-zinc-700 hover:bg-zinc-200" ${page === 1 ? "disabled" : ""}>‹</button>
            ${pageButtons}
            <button data-page="${Math.min(totalPages, page + 1)}" class="page-btn px-2 py-1.5 rounded-lg text-xs bg-zinc-100 text-zinc-700 hover:bg-zinc-200" ${page === totalPages ? "disabled" : ""}>›</button>
            <button data-page="${totalPages}" class="page-btn px-2 py-1.5 rounded-lg text-xs bg-zinc-100 text-zinc-700 hover:bg-zinc-200" ${page === totalPages ? "disabled" : ""}>»</button>
        </div>
    `;
}

function buildPageNumbers(current, totalPages) {
    if (totalPages <= 7) {
        return Array.from({ length: totalPages }, (_, i) => i + 1);
    }
    const pages = new Set([1, totalPages, current, current - 1, current + 1]);
    const sorted = [...pages].filter((n) => n >= 1 && n <= totalPages).sort((a, b) => a - b);
    const result = [];
    for (let i = 0; i < sorted.length; i += 1) {
        result.push(sorted[i]);
        if (i < sorted.length - 1 && sorted[i + 1] - sorted[i] > 1) {
            result.push("...");
        }
    }
    return result;
}

function openBoardModal(board = null) {
    document.getElementById("boardIdInput").value = board?.id || "";
    document.getElementById("boardSlugInput").value = board?.slug || "";
    document.getElementById("boardNameInput").value = board?.name || "";
    document.getElementById("boardDescInput").value = board?.description || "";
    document.getElementById("boardSortInput").value = String(board?.sort_order ?? 0);
    document.getElementById("boardIconInput").value = board?.icon || "";
    document.getElementById("boardActiveInput").checked = board ? !!board.is_active : true;
    boardDeleteBtnEl.classList.toggle("hidden", !board);
    boardModalEl.classList.remove("hidden");
}

function closeBoardModal() {
    boardModalEl.classList.add("hidden");
}

async function saveBoard(event) {
    event.preventDefault();
    const boardId = document.getElementById("boardIdInput").value;
    const payload = {
        slug: document.getElementById("boardSlugInput").value.trim(),
        name: document.getElementById("boardNameInput").value.trim(),
        description: document.getElementById("boardDescInput").value.trim(),
        sort_order: Number(document.getElementById("boardSortInput").value || 0),
        icon: document.getElementById("boardIconInput").value.trim(),
        is_active: document.getElementById("boardActiveInput").checked,
    };
    if (!payload.slug || !payload.name) {
        alert("slug와 이름은 필수입니다.");
        return;
    }
    if (boardId) {
        await secureFetch(`/api/boards/${boardId}`, { method: "PATCH", body: JSON.stringify(payload) });
    } else {
        await secureFetch("/api/boards", { method: "POST", body: JSON.stringify(payload) });
    }
    closeBoardModal();
    await loadBoards();
}

async function deleteBoard() {
    const boardId = document.getElementById("boardIdInput").value;
    if (!boardId) return;
    if (!confirm("게시판을 삭제(또는 비활성화)할까요?")) return;
    const result = await secureFetch(`/api/boards/${boardId}`, { method: "DELETE" });
    if (result.deactivated) {
        alert(result.detail || "게시판이 비활성화되었습니다.");
    }
    closeBoardModal();
    currentBoardId = null;
    await loadBoards();
}

async function openPostEditor(postId = null) {
    const board = currentBoard();
    if (!board) {
        alert("먼저 게시판을 선택해 주세요.");
        return;
    }
    if (postId) {
        const detail = await secureFetch(`/api/boards/posts/${postId}?with_view_count=false`);
        editingPostId = postId;
        postModalTitleEl.textContent = "게시글 수정";
        postTitleInputEl.value = detail.post.title || "";
        postPinnedInputEl.checked = !!detail.post.is_pinned;
        initEditor(detail.post.body_html || "");
        postDeleteBtnEl.classList.remove("hidden");
        renderEditorAttachmentList(detail.files);
    } else {
        const draft = await secureFetch(`/api/boards/${board.id}/posts`, {
            method: "POST",
            body: JSON.stringify({ title: "" }),
        });
        editingPostId = draft.id;
        postModalTitleEl.textContent = "게시글 작성";
        postTitleInputEl.value = "";
        postPinnedInputEl.checked = false;
        initEditor("");
        postDeleteBtnEl.classList.remove("hidden");
        renderEditorAttachmentList([]);
    }
    postModalEl.classList.remove("hidden");
    lockBodyScroll();
    resetScrollArea(postModalBodyEl);
}

function closePostModal() {
    teardownEditorImageControls();
    postModalEl.classList.add("hidden");
    unlockBodyScroll();
}

async function savePost(status) {
    if (!editingPostId || !editor) return;
    const payload = {
        title: postTitleInputEl.value.trim(),
        body_html: editor.getHTML(),
        is_pinned: postPinnedInputEl.checked,
        status,
    };
    await secureFetch(`/api/boards/posts/${editingPostId}`, {
        method: "PATCH",
        body: JSON.stringify(payload),
    });
    closePostModal();
    if (status === "published") {
        currentPage = 1;
        currentQuery = "";
        postSearchInputEl.value = "";
    }
    await loadBoards();
    await loadPosts(status === "published" ? 1 : currentPage);
    if (status === "published") {
        postListEl.scrollIntoView({ behavior: "smooth", block: "start" });
    }
}

async function deleteCurrentPost() {
    if (!editingPostId) return;
    if (!confirm("게시글을 삭제할까요?")) return;
    await secureFetch(`/api/boards/posts/${editingPostId}`, { method: "DELETE" });
    closePostModal();
    await loadPosts(1);
}

function renderEditorAttachmentList(files) {
    const attachmentFiles = (files || []).filter((file) => file.kind === "attachment");
    if (!attachmentFiles.length) {
        attachmentListEl.innerHTML = `<p class="text-xs text-zinc-500">첨부파일이 없습니다.</p>`;
        return;
    }
    attachmentListEl.innerHTML = attachmentFiles
        .map(
            (file) => `
            <div class="flex items-center justify-between text-xs bg-zinc-50 rounded-lg ring-1 ring-zinc-200 px-3 py-2">
                <span class="truncate">${escapeHtml(file.original_name)} (${Math.ceil((file.size_bytes || 0) / 1024)}KB)</span>
                <button class="file-delete-btn px-2 py-1 rounded bg-rose-50 text-rose-700" data-file-id="${file.id}">삭제</button>
            </div>
        `
        )
        .join("");
}

async function refreshEditingAttachments() {
    if (!editingPostId) return;
    const detail = await secureFetch(`/api/boards/posts/${editingPostId}?with_view_count=false`);
    renderEditorAttachmentList(detail.files);
}

async function uploadAttachments(files) {
    if (!editingPostId) return;
    const queue = Array.from(files || []);
    for (const file of queue) {
        const form = new FormData();
        form.append("file", file);
        await secureFetch(`/api/boards/posts/${editingPostId}/attachments`, { method: "POST", body: form });
    }
    await refreshEditingAttachments();
}

async function deleteAttachment(fileId) {
    if (!confirm("첨부파일을 삭제할까요?")) return;
    await secureFetch(`/api/boards/files/${fileId}`, { method: "DELETE" });
    await refreshEditingAttachments();
}

function injectMediaToken(html) {
    if (!html) return "";
    return html.replace(
        /(\/api\/boards\/media\/\d+)(?:\?token=[^"'>\s]*)?/g,
        `$1?token=${encodeURIComponent(authToken)}`
    );
}

async function openPostDetail(postId) {
    detailPostId = postId;
    const detail = await secureFetch(`/api/boards/posts/${postId}`);
    const post = detail.post;
    detailTitleEl.textContent = post.title || "(제목 없음)";
    detailMetaEl.textContent = `작성자 ${post.author_username} · ${formatDateTime(post.created_at)} · 조회 ${post.view_count}`;
    if (viewerInstance && typeof viewerInstance.destroy === "function") {
        viewerInstance.destroy();
    }
    detailViewerEl.innerHTML = "";
    viewerInstance = toastui.Editor.factory({
        el: detailViewerEl,
        viewer: true,
        initialValue: injectMediaToken(post.body_html || ""),
    });
    renderDetailAttachments(detail.files || []);
    renderComments(detail.comments || []);
    detailModalEl.classList.remove("hidden");
    lockBodyScroll();
    resetScrollArea(detailScrollAreaEl);
}

function closeDetailModal() {
    detailModalEl.classList.add("hidden");
    unlockBodyScroll();
}

function renderDetailAttachments(files) {
    const attachmentFiles = (files || []).filter((file) => file.kind === "attachment");
    if (!attachmentFiles.length) {
        detailAttachmentsEl.innerHTML = `<p class="text-xs text-zinc-500">첨부파일 없음</p>`;
        return;
    }
    detailAttachmentsEl.innerHTML = attachmentFiles
        .map(
            (file) => `
            <a href="/api/boards/media/${file.id}?token=${encodeURIComponent(authToken)}" target="_blank" class="block text-xs rounded-lg bg-zinc-50 ring-1 ring-zinc-200 px-3 py-2 hover:bg-zinc-100">
                ${escapeHtml(file.original_name)} (${Math.ceil((file.size_bytes || 0) / 1024)}KB)
            </a>
        `
        )
        .join("");
}

function renderComments(comments) {
    if (!comments.length) {
        commentListEl.innerHTML = `<p class="text-xs text-zinc-500">첫 댓글을 남겨보세요.</p>`;
        return;
    }
    commentListEl.innerHTML = comments
        .map((comment) => {
            const canEdit = comment.author_username === currentUsername;
            return `
                <div class="rounded-lg bg-zinc-50 ring-1 ring-zinc-200 px-3 py-2">
                    <p class="text-xs text-zinc-500">${escapeHtml(comment.author_username)} · ${formatDateTime(comment.updated_at || comment.created_at)}</p>
                    <p class="text-sm text-zinc-800 mt-1 whitespace-pre-wrap">${escapeHtml(comment.body)}</p>
                    ${
                        canEdit
                            ? `<div class="mt-1.5 flex justify-end gap-1">
                                <button class="comment-edit-btn text-[11px] px-2 py-1 rounded bg-zinc-100 text-zinc-600" data-comment-id="${comment.id}" data-comment-body="${escapeHtml(comment.body)}">수정</button>
                                <button class="comment-delete-btn text-[11px] px-2 py-1 rounded bg-rose-50 text-rose-700" data-comment-id="${comment.id}">삭제</button>
                            </div>`
                            : ""
                    }
                </div>
            `;
        })
        .join("");
}

async function submitComment() {
    if (!detailPostId) return;
    const body = commentInputEl.value.trim();
    if (!body) return;
    await secureFetch(`/api/boards/posts/${detailPostId}/comments`, {
        method: "POST",
        body: JSON.stringify({ body }),
    });
    commentInputEl.value = "";
    await openPostDetail(detailPostId);
}

async function editComment(commentId, currentBody) {
    const nextBody = prompt("댓글 수정", currentBody);
    if (nextBody === null) return;
    if (!nextBody.trim()) {
        alert("댓글 내용을 입력해 주세요.");
        return;
    }
    await secureFetch(`/api/boards/comments/${commentId}`, {
        method: "PATCH",
        body: JSON.stringify({ body: nextBody.trim() }),
    });
    await openPostDetail(detailPostId);
}

async function deleteComment(commentId) {
    if (!confirm("댓글을 삭제할까요?")) return;
    await secureFetch(`/api/boards/comments/${commentId}`, { method: "DELETE" });
    await openPostDetail(detailPostId);
}

function showBackupResult(message, isError = false) {
    backupResultMsgEl.textContent = message;
    backupResultMsgEl.classList.remove("hidden", "bg-emerald-50", "text-emerald-800", "bg-rose-50", "text-rose-800");
    backupResultMsgEl.classList.add(isError ? "bg-rose-50" : "bg-emerald-50", isError ? "text-rose-800" : "text-emerald-800");
}

async function loadBackupStatus() {
    const status = await secureFetch("/api/boards/backup/status");
    backupStatusBoxEl.innerHTML = `
        <p>DB ${status.db_exists ? "있음" : "없음"} · 이미지·첨부파일 ${status.local_file_count || 0}개</p>
    `;
    const pathsBox = document.getElementById("backupPathsBox");
    if (pathsBox) {
        pathsBox.innerHTML = `
            <p><span class="text-zinc-500">DB:</span> ${escapeHtml(status.db_path || "")}</p>
            <p><span class="text-zinc-500">파일:</span> ${escapeHtml(status.files_root || "")}/</p>
        `;
    }
    return status;
}

function openBackupModal() {
    backupResultMsgEl.classList.add("hidden");
    backupModalEl.classList.remove("hidden");
    loadBackupStatus().catch((error) => {
        backupStatusBoxEl.textContent = error.message;
    });
}

function closeBackupModal() {
    backupModalEl.classList.add("hidden");
}

async function downloadBackupZip() {
    const res = await fetch("/api/boards/backup/download", {
        headers: { Authorization: `Bearer ${authToken}` },
    });
    if (res.status === 401) {
        alert("인증 세션이 만료되었습니다.");
        location.href = "/";
        return;
    }
    if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || "백업 다운로드 실패");
    }
    const blob = await res.blob();
    const cd = res.headers.get("Content-Disposition") || "";
    const match = cd.match(/filename=\"?([^\";]+)\"?/);
    const filename = match ? match[1] : "board_backup.zip";
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
    showBackupResult("백업 ZIP 다운로드가 시작되었습니다.");
}

async function restoreBackupZip(file) {
    const mode = restoreModeSelectEl.value || "merge";
    if (mode === "replace" && !confirm("기존 게시판 데이터를 모두 삭제하고 복구합니다. 계속할까요?")) {
        return;
    }
    const form = new FormData();
    form.append("file", file);
    const res = await fetch(`/api/boards/backup/restore?mode=${encodeURIComponent(mode)}`, {
        method: "POST",
        headers: { Authorization: `Bearer ${authToken}` },
        body: form,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
        throw new Error(data.detail || "복구 실패");
    }
    showBackupResult(data.message || "글 데이터 복구가 완료되었습니다.");
    await loadBoards();
}

function bindEvents() {
    document.getElementById("goHomeBtn").addEventListener("click", () => {
        location.href = "/";
    });
    document.getElementById("boardBackupBtn").addEventListener("click", openBackupModal);
    document.getElementById("backupModalCloseBtn").addEventListener("click", closeBackupModal);
    document.getElementById("backupDownloadBtn").addEventListener("click", () => {
        downloadBackupZip().catch((error) => showBackupResult(error.message, true));
    });
    restoreFileInputEl.addEventListener("change", (event) => {
        const file = event.target.files?.[0];
        if (!file) return;
        restoreBackupZip(file)
            .catch((error) => showBackupResult(error.message, true))
            .finally(() => {
                restoreFileInputEl.value = "";
            });
    });
    document.getElementById("boardCreateBtn").addEventListener("click", () => openBoardModal());
    document.getElementById("boardModalCloseBtn").addEventListener("click", closeBoardModal);
    boardFormEl.addEventListener("submit", (event) => {
        saveBoard(event).catch((error) => alert(error.message));
    });
    boardDeleteBtnEl.addEventListener("click", () => {
        deleteBoard().catch((error) => alert(error.message));
    });

    postCreateBtnEl.addEventListener("click", () => {
        openPostEditor().catch((error) => alert(error.message));
    });
    postExcelBtnEl.addEventListener("click", openExcelImportModal);
    document.getElementById("excelImportModalCloseBtn").addEventListener("click", closeExcelImportModal);
    excelTemplateDownloadBtnEl.addEventListener("click", () => {
        downloadPostExcelTemplate().catch((error) => showExcelImportResult(error.message, true));
    });
    postExcelInputEl.addEventListener("change", (event) => {
        const file = event.target.files?.[0];
        if (!file) return;
        pendingExcelFile = file;
        excelSelectedFileNameEl.textContent = file.name;
        setExcelSaveEnabled(false);
        renderExcelValidationErrors([]);
        excelImportResultMsgEl.classList.add("hidden");
        validatePostExcel(file).catch((error) => {
            setExcelSaveEnabled(false);
            renderExcelValidationErrors([]);
            showExcelImportResult(error.message, true);
        });
    });
    excelSaveBtnEl.addEventListener("click", () => {
        if (!pendingExcelFile || !excelImportValidated) return;
        excelSaveBtnEl.disabled = true;
        excelSaveBtnEl.textContent = "저장 중...";
        uploadPostExcel(pendingExcelFile)
            .catch((error) => showExcelImportResult(error.message, true))
            .finally(() => {
                if (!excelImportModalEl.classList.contains("hidden")) {
                    excelSaveBtnEl.textContent = "저장하기";
                    setExcelSaveEnabled(excelImportValidated);
                }
            });
    });
    document.getElementById("postModalCloseBtn").addEventListener("click", closePostModal);
    document.getElementById("postSaveDraftBtn").addEventListener("click", () => {
        savePost("draft").catch((error) => alert(error.message));
    });
    document.getElementById("postPublishBtn").addEventListener("click", () => {
        savePost("published").catch((error) => alert(error.message));
    });
    postDeleteBtnEl.addEventListener("click", () => {
        deleteCurrentPost().catch((error) => alert(error.message));
    });

    attachmentInputEl.addEventListener("change", (event) => {
        uploadAttachments(event.target.files)
            .catch((error) => alert(error.message))
            .finally(() => {
                attachmentInputEl.value = "";
            });
    });

    document.getElementById("detailCloseBtn").addEventListener("click", closeDetailModal);
    document.getElementById("detailEditBtn").addEventListener("click", () => {
        closeDetailModal();
        openPostEditor(detailPostId).catch((error) => alert(error.message));
    });
    commentSubmitBtnEl.addEventListener("click", () => {
        submitComment().catch((error) => alert(error.message));
    });
    commentInputEl.addEventListener("keydown", (event) => {
        if (event.key === "Enter") {
            event.preventDefault();
            submitComment().catch((error) => alert(error.message));
        }
    });

    document.getElementById("postSearchBtn").addEventListener("click", () => {
        currentQuery = postSearchInputEl.value.trim();
        loadPosts(1).catch((error) => alert(error.message));
    });
    postSearchInputEl.addEventListener("keydown", (event) => {
        if (event.key === "Enter") {
            event.preventDefault();
            currentQuery = postSearchInputEl.value.trim();
            loadPosts(1).catch((error) => alert(error.message));
        }
    });

    boardListEl.addEventListener("click", (event) => {
        const target = event.target;
        const editBtn = target.closest(".board-edit-btn");
        if (editBtn) {
            event.stopPropagation();
            const board = boards.find((row) => row.id === Number(editBtn.dataset.boardEditId));
            if (board) openBoardModal(board);
            return;
        }
        const card = target.closest(".board-card");
        if (card) {
            selectBoard(Number(card.dataset.boardId));
        }
    });

    boardListEl.addEventListener("keydown", (event) => {
        if (event.key !== "Enter" && event.key !== " ") return;
        const card = event.target.closest(".board-card");
        if (!card || event.target.closest(".board-edit-btn")) return;
        event.preventDefault();
        selectBoard(Number(card.dataset.boardId));
    });

    postListEl.addEventListener("click", (event) => {
        const target = event.target;
        const detailBtn = target.closest(".post-detail-btn");
        if (detailBtn) {
            openPostDetail(Number(detailBtn.dataset.postId)).catch((error) => alert(error.message));
            return;
        }
        const editBtn = target.closest(".post-edit-btn");
        if (editBtn) {
            openPostEditor(Number(editBtn.dataset.postId)).catch((error) => alert(error.message));
        }
    });

    attachmentListEl.addEventListener("click", (event) => {
        const target = event.target;
        const deleteBtn = target.closest(".file-delete-btn");
        if (!deleteBtn) return;
        deleteAttachment(Number(deleteBtn.dataset.fileId)).catch((error) => alert(error.message));
    });

    commentListEl.addEventListener("click", (event) => {
        const target = event.target;
        const editBtn = target.closest(".comment-edit-btn");
        if (editBtn) {
            const raw = editBtn.dataset.commentBody || "";
            const textarea = document.createElement("textarea");
            textarea.innerHTML = raw;
            editComment(Number(editBtn.dataset.commentId), textarea.value).catch((error) => alert(error.message));
            return;
        }
        const deleteBtn = target.closest(".comment-delete-btn");
        if (deleteBtn) {
            deleteComment(Number(deleteBtn.dataset.commentId)).catch((error) => alert(error.message));
        }
    });

    postPaginationEl.addEventListener("click", (event) => {
        const target = event.target;
        const pageBtn = target.closest(".page-btn");
        if (!pageBtn || pageBtn.disabled) return;
        const page = Number(pageBtn.dataset.page || "1");
        loadPosts(page)
            .then(() => {
                postListEl.scrollIntoView({ behavior: "smooth", block: "start" });
            })
            .catch((error) => alert(error.message));
    });
}

function bootstrap() {
    authToken = localStorage.getItem("vcall_token") || "";
    currentUsername = localStorage.getItem("vcall_username") || "";
    if (!authToken) {
        location.href = "/";
        return;
    }
    bindEvents();
    loadAppVersionBadge();
    bindVersionModal();
    loadBoards().catch((error) => alert(error.message));
}

window.addEventListener("DOMContentLoaded", bootstrap);
