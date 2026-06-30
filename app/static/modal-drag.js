(function () {
    const MOBILE_QUERY = "(max-width: 639px)";
    const VIEWPORT_MARGIN = 16;
    const modalOffsets = new WeakMap();
    const modalConfigs = new WeakMap();
    let stylesInjected = false;
    let resizeBound = false;

    function isModalMovable() {
        return !window.matchMedia(MOBILE_QUERY).matches;
    }

    function injectStyles() {
        if (stylesInjected) return;
        stylesInjected = true;
        const style = document.createElement("style");
        style.textContent = `
            @media (min-width: 640px) {
                [data-draggable-modal]:not(.hidden) {
                    display: flex !important;
                    align-items: center;
                    justify-content: center;
                }
                .modal-draggable-panel {
                    position: relative !important;
                    left: auto !important;
                    top: auto !important;
                    margin: 0 !important;
                    flex-shrink: 0;
                    max-height: min(92vh, calc(100vh - 2rem));
                    transform: translate(var(--modal-drag-x, 0px), var(--modal-drag-y, 0px));
                }
            }
            @media (max-width: 639px) {
                .modal-draggable-panel {
                    position: relative !important;
                    left: auto !important;
                    top: auto !important;
                    transform: none !important;
                }
            }
            .modal-drag-handle {
                touch-action: none;
            }
            @media (min-width: 640px) {
                .modal-drag-handle {
                    cursor: grab;
                }
                body.modal-panel-dragging .modal-drag-handle {
                    cursor: grabbing;
                }
            }
            body.modal-panel-dragging {
                user-select: none;
            }
        `;
        document.head.appendChild(style);
    }

    function getOffset(overlay) {
        if (!modalOffsets.has(overlay)) {
            modalOffsets.set(overlay, { x: 0, y: 0 });
        }
        return modalOffsets.get(overlay);
    }

    function clampOffset(config, x, y) {
        if (!isModalMovable()) {
            return { x: 0, y: 0 };
        }
        const { overlay, panel } = config;
        const offset = { x, y };
        const prev = getOffset(overlay);
        prev.x = x;
        prev.y = y;
        applyPosition(config, true);

        const rect = panel.getBoundingClientRect();
        const maxLeft = VIEWPORT_MARGIN;
        const maxTop = VIEWPORT_MARGIN;
        const maxRight = window.innerWidth - VIEWPORT_MARGIN;
        const maxBottom = window.innerHeight - VIEWPORT_MARGIN;

        if (rect.left < maxLeft) {
            offset.x += maxLeft - rect.left;
        }
        if (rect.top < maxTop) {
            offset.y += maxTop - rect.top;
        }
        if (rect.right > maxRight) {
            offset.x -= rect.right - maxRight;
        }
        if (rect.bottom > maxBottom) {
            offset.y -= rect.bottom - maxBottom;
        }

        prev.x = offset.x;
        prev.y = offset.y;
        return offset;
    }

    function applyPosition(config, skipClamp = false) {
        const { overlay, panel } = config;
        if (!panel) return;
        if (!isModalMovable()) {
            panel.style.removeProperty("--modal-drag-x");
            panel.style.removeProperty("--modal-drag-y");
            return;
        }
        let { x, y } = getOffset(overlay);
        if (!skipClamp) {
            ({ x, y } = clampOffset(config, x, y));
        }
        panel.style.setProperty("--modal-drag-x", `${x}px`);
        panel.style.setProperty("--modal-drag-y", `${y}px`);
    }

    function resetDraggableModal(overlay) {
        if (!overlay) return;
        modalOffsets.set(overlay, { x: 0, y: 0 });
        const config = modalConfigs.get(overlay);
        if (config) applyPosition(config);
    }

    function bindDrag(config) {
        const { overlay, panel, handle } = config;
        if (!handle || !panel) return;

        let dragState = null;

        const onPointerMove = (event) => {
            if (!dragState) return;
            const rawX = dragState.originX + (event.clientX - dragState.startX);
            const rawY = dragState.originY + (event.clientY - dragState.startY);
            const { x, y } = clampOffset(config, rawX, rawY);
            getOffset(overlay).x = x;
            getOffset(overlay).y = y;
            applyPosition(config, true);
        };

        const endDrag = () => {
            dragState = null;
            document.body.classList.remove("modal-panel-dragging");
            window.removeEventListener("pointermove", onPointerMove);
            window.removeEventListener("pointerup", endDrag);
            window.removeEventListener("pointercancel", endDrag);
        };

        handle.addEventListener("pointerdown", (event) => {
            if (!isModalMovable()) return;
            if (event.target.closest("button")) return;
            if (event.button !== 0) return;
            event.preventDefault();
            const offset = getOffset(overlay);
            dragState = {
                startX: event.clientX,
                startY: event.clientY,
                originX: offset.x,
                originY: offset.y,
            };
            document.body.classList.add("modal-panel-dragging");
            window.addEventListener("pointermove", onPointerMove);
            window.addEventListener("pointerup", endDrag);
            window.addEventListener("pointercancel", endDrag);
        });

        handle.addEventListener("dblclick", (event) => {
            if (!isModalMovable()) return;
            if (event.target.closest("button")) return;
            resetDraggableModal(overlay);
        });
    }

    function resolvePanel(overlay, panelSelector) {
        if (panelSelector) {
            return overlay.querySelector(panelSelector) || overlay.querySelector("[data-modal-panel]");
        }
        return (
            overlay.querySelector("[data-modal-panel]") ||
            overlay.querySelector(".modal-draggable-panel") ||
            overlay.firstElementChild
        );
    }

    function resolveHandle(panel, handleSelector) {
        if (handleSelector) {
            return panel.querySelector(handleSelector) || panel.querySelector("[data-modal-drag-handle]");
        }
        return (
            panel.querySelector("[data-modal-drag-handle]") ||
            panel.querySelector(".modal-drag-handle")
        );
    }

    function initDraggableModal(options) {
        injectStyles();
        const overlay = options.overlay || options.overlayEl;
        if (!overlay) return null;

        const panel = options.panel || resolvePanel(overlay, options.panelSelector);
        const handle = options.handle || resolveHandle(panel, options.handleSelector);
        if (!panel || !handle) return null;

        panel.classList.add("modal-draggable-panel");
        handle.classList.add("modal-drag-handle");
        if (!handle.title) {
            handle.title = "헤더를 드래그해 이동 · 더블클릭 시 가운데";
        }

        const config = { overlay, panel, handle };
        modalConfigs.set(overlay, config);
        getOffset(overlay);
        bindDrag(config);
        applyPosition(config);
        return config;
    }

    function initAllDraggableModals() {
        injectStyles();
        document.querySelectorAll("[data-draggable-modal]").forEach((overlay) => {
            if (modalConfigs.has(overlay)) return;
            initDraggableModal({
                overlay,
                panelSelector: overlay.dataset.modalPanel,
                handleSelector: overlay.dataset.modalHandle,
            });
        });

        if (!resizeBound) {
            resizeBound = true;
            window.addEventListener("resize", () => {
                modalConfigs.forEach((config) => {
                    if (config.overlay.classList.contains("hidden")) {
                        if (!isModalMovable()) resetDraggableModal(config.overlay);
                        return;
                    }
                    const offset = getOffset(config.overlay);
                    const clamped = clampOffset(config, offset.x, offset.y);
                    getOffset(config.overlay).x = clamped.x;
                    getOffset(config.overlay).y = clamped.y;
                    applyPosition(config, true);
                });
            });
        }
    }

    window.initDraggableModal = initDraggableModal;
    window.initAllDraggableModals = initAllDraggableModals;
    window.resetDraggableModal = resetDraggableModal;
})();
