(function () {
    const MOBILE_QUERY = "(max-width: 639px)";
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
                .modal-draggable-panel {
                    position: fixed !important;
                    left: 50%;
                    top: 50%;
                    margin-left: 0 !important;
                    margin-right: 0 !important;
                    max-height: 92vh;
                    transform: translate(calc(-50% + var(--modal-drag-x, 0px)), calc(-50% + var(--modal-drag-y, 0px)));
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

    function applyPosition(config) {
        const { overlay, panel } = config;
        if (!panel) return;
        if (!isModalMovable()) {
            panel.style.removeProperty("--modal-drag-x");
            panel.style.removeProperty("--modal-drag-y");
            return;
        }
        const { x, y } = getOffset(overlay);
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
            const offset = getOffset(overlay);
            offset.x = dragState.originX + (event.clientX - dragState.startX);
            offset.y = dragState.originY + (event.clientY - dragState.startY);
            applyPosition(config);
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
                    applyPosition(config);
                });
            });
        }
    }

    window.initDraggableModal = initDraggableModal;
    window.initAllDraggableModals = initAllDraggableModals;
    window.resetDraggableModal = resetDraggableModal;
})();
