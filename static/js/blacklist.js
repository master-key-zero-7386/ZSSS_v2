// =====================================================
// ファイル名: static/js/blacklist.js
// 目的： ブラックリスト
// =====================================================

document.addEventListener("DOMContentLoaded", () => {
    // --- ▼ SECTION 01: BrackList登録 ▼ ---
    const fileInput = document.getElementById("blacklistCsvFileInput");
    const fileName  = document.getElementById("blacklistCsvFileName");
    const uploadBtn = document.getElementById("blacklistCsvUploadBtn");

    if (fileInput && fileName && uploadBtn) {

        // ファイル選択（テキストクリック）
        fileName.addEventListener("click", () => {
            fileInput.click();
        });

        // ファイル名表示
        fileInput.addEventListener("change", () => {
            if (fileInput.files.length > 0) {
                fileName.value = fileInput.files[0].name;
            }
        });

        // CSVアップロード
        uploadBtn.addEventListener("click", async () => {

            if (!fileInput.files.length) {
                alert("CSVファイルを選択してください");
                return;
            }

            // ★ トップCSVと同じ：Globalプルダウンから country_code を取得
            const globalRegionEl = document.getElementById("globalRegion");
            if (!globalRegionEl || !globalRegionEl.value) {
                alert("リージョンが取得できません");
                return;
            }

            const formData = new FormData();
            formData.append("file", fileInput.files[0]);
            formData.append("country_code", globalRegionEl.value);

            try {
                const res = await fetch("/blacklist/import", {
                    method: "POST",
                    body: formData
                });

                const data = await res.json();

                if (data.status !== "success") {

                    // CSV形式エラーなどは confirm モーダルで明示
                    if (data.message) {
                        await showConfirmModal({
                            contentHtml: `
                                <h3>CSV形式エラー</h3>

                                <p>このCSVは使用できません。</p>

                                <p>
                                    ブラックリスト登録は、<br>
                                    専用の初期CSVファイルをダウンロードして作成してください。
                                </p>

                                <div class="ui-confirm-actions">
                                    <button
                                        class="ui-confirm-btn ui-confirm-btn-primary"
                                        data-confirm="ok">
                                        OK
                                    </button>
                                </div>
                            `
                        });
                    } else {
                        alert("CSV取り込みに失敗しました");
                    }

                    return;
                }

                alert(
                    "ブラックリストCSV取り込み完了\n\n" +

                    "[ASIN]\n" +
                    `取り込み前件数：${data.asin.before}\n` +
                    `今回追加件数：${data.asin.import}\n` +
                    `現在件数：${data.asin.after}\n\n` +

                    "[BRAND]\n" +
                    `取り込み前件数：${data.brand.before}\n` +
                    `今回追加件数：${data.brand.import}\n` +
                    `現在件数：${data.brand.after}`
                );

                // リセット
                fileInput.value = "";
                fileName.value  = "";

            } catch (e) {
                alert("通信エラーが発生しました");
            }
        });
    }

    // --- ▼ SECTION 02: CSV Output ▼ ---
    document.getElementById("blacklistCsvExportBtn")?.addEventListener("click", () => {
        const globalRegionEl = document.getElementById("globalRegion");
        if (!globalRegionEl || !globalRegionEl.value) {
            alert("リージョンが取得できません");
            return;
        }

        window.location.href = `/blacklist/export/${globalRegionEl.value}`;
    });

    // --- ▼ SECTION 03: DataTable 初期化 ▼ ---
    const brandTableEl = document.getElementById("brandTable");
    const asinTableEl  = document.getElementById("asinTable");

    let brandTable = null; 
    if (brandTableEl) {
        brandTable = $('#brandTable').DataTable({
            pageLength: 100,
            scrollY: "500px",
            // scrollX: true,
            scrollCollapse: true,
            paging: true,   

            autoWidth: false,
            columnDefs: [
                { width: "30%", targets: 0 },
                { width: "40%", targets: 1 },
                { width: "20%", targets: 2 },
                { width: "10%", targets: 3 }
            ]  
        });
        setTimeout(() => {
            brandTable.columns.adjust();
        }, 100);        
    }

    let asinTable = null; 
    if (asinTableEl) {
        $('#asinTable').DataTable({
            pageLength: 100,
            scrollY: "500px",
            // scrollX: true,
            scrollCollapse: true,
            paging: true,   

            autoWidth: false,
            columnDefs: [
                { width: "30%", targets: 0 },
                { width: "40%", targets: 1 },
                { width: "20%", targets: 2 },
                { width: "10%", targets: 3 }
            ]                     
        });
        setTimeout(() => {
            $('#asinTable').DataTable().columns.adjust();
        }, 100);        
    }   

    if (brandTable) {

        const interval = setInterval(() => {
            const el = document.getElementById("globalRegion");

            if (el && el.value) {
                clearInterval(interval);
                loadBrandList();
                loadAsinList();
            }
        }, 200);

    }

    document.getElementById("globalRegion")?.addEventListener("change", () => {
        loadBrandList();
        loadAsinList();
    });    

    // --- ▼ SECTION 04: Brand一覧取得 ▼ ---
    async function loadBrandList() {
        const el = document.getElementById("globalRegion");
        const country_code = el ? el.value : null;
        if (!country_code) return;

        const res = await fetch(`/blacklist/brand/${country_code}`);
        const data = await res.json();

        const rows = data.rows || [];
        const table = brandTable;

        table.clear();

        rows.forEach(row => {

            const node = table.row.add([

                row.brand,
                `<span class="note-text">${row.note || ""}</span>`,
                row.created_at,
                `
                <button class="btn-blue btn-edit">編集</button>
                <button class="btn-blue btn-save" style="display:none;">保存</button>
                <button class="btn-cancel btn-cancel-action" style="display:none;">キャンセル</button>
                <button class="btn-delete btn-delete-action">削除</button>
                `
            ]).node();

            node.dataset.id = row.id;
        });

        table.draw();
    }

    // --- ▼ SECTION 05: ASIN一覧取得 ▼ ---
    async function loadAsinList() {
        const el = document.getElementById("globalRegion");
        const country_code = el ? el.value : null;
        if (!country_code) return;

        const res = await fetch(`/blacklist/asin/${country_code}`);
        const data = await res.json();

        const rows = data.rows || [];
        const table = $('#asinTable').DataTable();

        table.clear();

        rows.forEach(row => {

            const node = table.row.add([
                
                row.asin,
                `<span class="note-text">${row.note || ""}</span>`,
                row.created_at,
                `
                <button class="btn-blue btn-edit">編集</button>
                <button class="btn-blue btn-save" style="display:none;">保存</button>
                <button class="btn-cancel btn-cancel-action" style="display:none;">キャンセル</button>
                <button class="btn-delete btn-delete-action">削除</button>
                `
            ]).node();

            node.dataset.id = row.id;
        });

        table.draw();
    }

    // --- ▼ SECTION 06:  ▼ ---
    document.querySelectorAll(".bl-tab").forEach(btn => {
        btn.addEventListener("click", () => {

            document.querySelectorAll(".bl-tab").forEach(b => b.classList.remove("active"));
            document.querySelectorAll(".bl-tab-content").forEach(c => c.classList.remove("active"));

            btn.classList.add("active");
            const target = document.getElementById("tab-" + btn.dataset.tab);
            target.classList.add("active");

            // ←ここが追加部分
            setTimeout(() => {
                if (btn.dataset.tab === "brand") {
                    brandTable.columns.adjust();
                } else {
                    $('#asinTable').DataTable().columns.adjust();
                }
            }, 50);
            const input = document.getElementById("newMain");
            input.placeholder = btn.dataset.tab === "brand" ? "Brand" : "ASIN";
        });
    });

    // --- ▼ SECTION 07: Blacklist 操作まとめ ▼ ---
    document.addEventListener("click", async (e) => {

        const tr = e.target.closest("tr");
        if (!tr) return;

        const cells = tr.querySelectorAll("td");

        // =========================
        // 編集
        // =========================
        if (e.target.classList.contains("btn-edit")) {

            const mainText = cells[0].textContent;
            const noteText = cells[1].textContent;

            tr.dataset.originalMain = mainText;
            tr.dataset.originalNote = noteText;

            cells[0].innerHTML = `<input type="text" class="edit-main" value="${mainText}">`;
            cells[1].innerHTML = `<input type="text" class="edit-note" value="${noteText}">`;

            tr.querySelector(".btn-edit").style.display = "none";
            tr.querySelector(".btn-save").style.display = "inline-block";
            tr.querySelector(".btn-cancel").style.display = "inline-block";
        }

        // =========================
        // キャンセル
        // =========================
        if (e.target.classList.contains("btn-cancel")) {

            const main = tr.dataset.originalMain;
            const note = tr.dataset.originalNote;

            cells[0].textContent = main;
            cells[1].innerHTML = `<span class="note-text">${note}</span>`;

            // tr.querySelector(".btn-edit").style.display = "inline-block";
            // tr.querySelector(".btn-save").style.display = "none";
            // tr.querySelector(".btn-cancel").style.display = "none";
            (tr.querySelector(".btn-edit")   || {}).style && (tr.querySelector(".btn-edit").style.display = "inline-block");  // ここを修正
            (tr.querySelector(".btn-save")   || {}).style && (tr.querySelector(".btn-save").style.display = "none");          // ここを修正
            (tr.querySelector(".btn-cancel") || {}).style && (tr.querySelector(".btn-cancel").style.display = "none");        // ここを修正            
        }

        // =========================
        // 保存
        // =========================
        if (e.target.classList.contains("btn-save")) {

            const row_id = tr.dataset.id;

            const main = cells[0].querySelector("input")
                ? cells[0].querySelector("input").value
                : cells[0].textContent;

            const note = cells[1].querySelector("input")
                ? cells[1].querySelector("input").value
                : cells[1].textContent;

            const el = document.getElementById("globalRegion");
            const country_code = el ? el.value : null;

            const res = await fetch("/blacklist/update", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({
                    id: row_id,
                    country_code: country_code,
                    main: main,
                    note: note,
                    target: document.querySelector(".bl-tab.active")?.dataset.tab
                })
            });

            const data = await res.json();

            if (data.status !== "ok") {  
                alert(data.message);
                return;
            }            

            cells[0].textContent = main;
            cells[1].innerHTML = `<span class="note-text">${note}</span>`;

            tr.querySelector(".btn-edit").style.display = "inline-block";
            tr.querySelector(".btn-save").style.display = "none";
            tr.querySelector(".btn-cancel").style.display = "none";
        }

        // =========================
        // 削除
        // =========================
        if (e.target.classList.contains("btn-delete")) {

            const row_id = tr.dataset.id;
            const main = cells[0].textContent;

            if (!confirm(`削除しますか？\n\n${main}`)) return;

            const el = document.getElementById("globalRegion");
            const country_code = el ? el.value : null;

            await fetch("/blacklist/delete", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({
                    id: row_id,
                    country_code: country_code,
                })
            });

            $(tr).closest('table').DataTable().row(tr).remove().draw(false);
        }

    });

    // --- ▼ 追加ボタン処理（ここ追加） ▼ ---
    document.getElementById("addBtn")?.addEventListener("click", async () => {

        const main = document.getElementById("newMain").value.trim();
        const note = document.getElementById("newNote").value.trim();

        if (!main) {
            alert("値を入力してください");
            return;
        }

        const el = document.getElementById("globalRegion");
        const country_code = el ? el.value : null;

        if (!country_code) {
            alert("リージョンが取得できません");
            return;
        }

        const res = await fetch("/blacklist/add", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                id: 0,   // ←新規なのでダミー
                country_code: country_code,
                main: main,
                note: note,
                target: document.querySelector(".bl-tab.active")?.dataset.tab
            })
        });

        const data = await res.json();

        if (data.status !== "ok") {
            alert(data.message || "追加失敗");
            return;
        }

        showToast("追加しました");

        // リロード
        loadBrandList();
        loadAsinList();

        // 入力クリア
        document.getElementById("newMain").value = "";
        document.getElementById("newNote").value = "";
    });

    // --- ▼ トースト表示（ここ追加） ▼ ---
    function showToast(msg) {
        let toast = document.createElement("div");
        toast.textContent = msg;

        Object.assign(toast.style, {
            position: "fixed",
            bottom: "30px",
            right: "30px",
            background: "#333",
            color: "#fff",
            padding: "12px 18px",
            borderRadius: "6px",
            fontSize: "14px",
            zIndex: 9999,
            opacity: 0,
            transition: "opacity 0.3s"
        });

        document.body.appendChild(toast);

        setTimeout(() => toast.style.opacity = 1, 10);

        setTimeout(() => {
            toast.style.opacity = 0;
            setTimeout(() => toast.remove(), 300);
        }, 2000);
    }

}); // DOMC終了
 






