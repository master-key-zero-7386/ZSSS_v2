// =====================================================
// ファイル名: static/js/ui_confirm.js
// 目的： ポップアップに使用　共通ダイアログ
// =====================================================

function ensureConfirmBase() {
    if (document.getElementById("uiConfirmOverlay")) return;

    const html = `

    <style>
        /* ===== 共通 Confirm ボタン ===== */
        .ui-confirm-actions {
            display: flex;
            justify-content: flex-end;
            gap: 10px;
            margin-top: 20px;
        }
        .ui-confirm-btn {
            padding: 10px 18px;
            font-size: 14px;
            border-radius: 4px;
            cursor: pointer;
            line-height: 1.2;
        }
        .ui-confirm-btn-primary {
            background: #0d6efd;
            color: #fff;
            border: none;
            font-weight: 600;
        }
        .ui-confirm-btn-cancel {
            background: #f5f5f5;
            color: #333;
            border: 1px solid #ccc;
        }
    </style>    

    <div id="uiConfirmOverlay" style="
        display:flex;
        opacity:0;
        pointer-events:none;
        position:fixed;
        inset:0;
        background:rgba(0,0,0,0.5);
        z-index:9999;
        align-items:center;
        justify-content:center;
        transition: opacity 0.25s ease;
    ">
        <div id="uiConfirmModal" style="
            background:#fff;
            width:420px;
            max-width:90%;
            padding:20px;
            border-radius:6px;
            transform: translateY(-10px);
            transition: transform 0.25s ease;
        ">
            <!-- ★ 中身は完全に差し替え -->
            <div id="uiConfirmContent"></div>
        </div>
    </div>
    `;
    document.body.insertAdjacentHTML("beforeend", html);
}

// --- ▼ 共通 Confirm（slot方式） ▼ ---
window.showConfirmModal = function ({ contentHtml } = {}) {
    ensureConfirmBase();

    return new Promise((resolve) => {
        const overlay = document.getElementById("uiConfirmOverlay");
        const modal   = document.getElementById("uiConfirmModal");
        const content = document.getElementById("uiConfirmContent");

        content.innerHTML = contentHtml;

        overlay.style.pointerEvents = "auto";
        overlay.style.opacity = "1";
        modal.style.transform = "translateY(0)";

        const close = (result) => {
            overlay.style.opacity = "0";
            overlay.style.pointerEvents = "none";
            modal.style.transform = "translateY(-10px)";
            resolve(result);
        };

        // ★ data-confirm 属性を持つ要素を全部拾う
        content.querySelectorAll("[data-confirm]").forEach(btn => {
            btn.onclick = () => close(btn.dataset.confirm);
        });
    });
};





