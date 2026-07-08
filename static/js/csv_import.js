// =====================================================
// ファイル名: static/js/csv_import.js
// 目的: CSVファイルからListing DBへの登録
// =====================================================

document.addEventListener("DOMContentLoaded", () => {
    const uploadBtn = document.getElementById("csvUploadBtn");
    const fileInput = document.getElementById("csvFileInput");
    const fileNameBox = document.getElementById("csvFileName");
    const resultArea = document.getElementById("csvResultArea");

    const asinInput = document.getElementById("asinInput");
    const asinAddBtn = document.getElementById("asinAddBtn");

    // 枠をクリックしたら file input を開く
    if (fileNameBox) {
        fileNameBox.addEventListener("click", () => {
            fileInput.click();
        });
    }

    // ファイル選択したら枠にファイル名を表示
    if (fileInput) {
        fileInput.addEventListener("change", (e) => {
            const fileName = e.target.files.length ? e.target.files[0].name : "";
            fileNameBox.value = fileName;
        });
    }

    // 「アップロード」ボタン処理
    if (uploadBtn) {
        uploadBtn.addEventListener("click", () => {
            if (!fileInput.files.length) {
                alert("CSVファイルを選択してください");
                return;
            }

            // 事前リセット（古いメッセージや件数を消す）
            // const overlay = document.getElementById("loadingOverlay");
            const message = document.getElementById("loadingMessage");
            const countEl = document.getElementById("csvCount");
            if (message) message.textContent = "";
            if (countEl) countEl.textContent = "";

            const formData = new FormData();
            formData.append("file", fileInput.files[0]);
            formData.append("country_code", document.getElementById("globalRegion").value);

           
            // if (overlay) overlay.style.display = "flex";

            fetch("/csv/csv_import", {
                method: "POST",
                body: formData
            })
            .then(response => response.json())
            .then(data => {
                // テーブル更新処理（従来通り）
                if (data.status === "success") {
                    let okTable = $('#csvOkTable').DataTable();
                    let listedTable = $('#csvListedTable').DataTable();
                    let blacklistTable = $('#csvBlacklistTable').DataTable();

                    okTable.clear();
                    listedTable.clear();     
                    blacklistTable.clear();

                    (data.ok || []).forEach(item => okTable.row.add(item));
                    (data.listed || []).forEach(item => listedTable.row.add(item)); 
                    (data.blacklist || []).forEach(item => blacklistTable.row.add(item));

                    okTable.draw();
                    listedTable.draw();   
                    blacklistTable.draw();

                } else {
                    const errMsg = data && data.message ? data.message : "CSV処理に失敗しました";
                    if (message) message.textContent = errMsg;
                    if (countEl) countEl.textContent = errMsg;
                    window.showToast(errMsg, "error");  
                }
            })
            .catch(err => {
                const errMsg = "エラーが発生しました";
                if (message) message.textContent = errMsg;
                if (countEl) countEl.textContent = errMsg;
                console.error("[CSV Upload] error:", err);
                window.showToast("エラー: " + err, "error");
            })
            .finally(() => {
                // overlay は閉じるが、件数は csvCount に残す（履歴は上書き済み）
                // if (overlay) overlay.style.display = "none";
                // message は残す（ユーザーが確認できる）
            });
        });
    }

    // ASIN直接UPLOAD
    if (asinAddBtn) {
        asinAddBtn.addEventListener("click", () => {

            const asin = asinInput.value.trim().toUpperCase();

            if (!asin) {
                alert("ASINを入力してください");
                return;
            }

            const table = $("#csvOkTable").DataTable();

            const exists = table
                .rows()
                .data()
                .toArray()
                .some(row => row.asin === asin);

            if (exists) {
                window.showToast("重複しています", "error");
                return;
            }

            const formData = new FormData();

            formData.append("asin", asin);
            formData.append(
                "country_code",
                document.getElementById("globalRegion").value
            );

            fetch("/csv/check", {
                method: "POST",
                body: formData
            })
            .then(response => response.json())
            .then(data => {

                if (data.status === "success") {

                    let okTable = $('#csvOkTable').DataTable();
                    let listedTable = $('#csvListedTable').DataTable();
                    let blacklistTable = $('#csvBlacklistTable').DataTable();

                    (data.ok || []).forEach(item => okTable.row.add(item));
                    (data.listed || []).forEach(item => listedTable.row.add(item));
                    (data.blacklist || []).forEach(item => blacklistTable.row.add(item));

                    okTable.draw();
                    listedTable.draw();
                    blacklistTable.draw();
                    asinInput.value = "";
                }
            })
            .catch(err => {
                console.error(err);
            });
        });
    }

    // ASIN Enter追加
    if (asinInput) {

        asinInput.addEventListener("keypress", (e) => {

            if (e.key === "Enter") {

                e.preventDefault();

                asinAddBtn.click();
            }
        });
    }    

    // DataTables 初期化
    $('#csvOkTable').DataTable({
        pageLength: 10,
        lengthChange: false,
        searching: false,
        info: false,
        columns: [
            { data: "asin", title: "ASIN" },
            { data: "sku",  title: "SKU" }
        ],
        language: {
            paginate: {
                previous: "前へ",
                next: "次へ"
            },
            info: "全 _TOTAL_ 件中 _START_ から _END_ を表示",
            infoEmpty: "0 件中 0 から 0 を表示",
            emptyTable: "データがありません"
        }
    }); 

    $('#csvListedTable').DataTable({
        pageLength: 10,
        lengthChange: false,
        searching: false,
        info: false,
        columns: [
            { data: "asin", title: "ASIN" },
            { data: "sku",  title: "" }
        ],
        language: {
            paginate: {
                previous: "前へ",
                next: "次へ"
            },
            info: "全 _TOTAL_ 件中 _START_ から _END_ を表示",
            infoEmpty: "0 件中 0 から 0 を表示",
            emptyTable: "データがありません"
        }
    }); 

    $('#csvBlacklistTable').DataTable({
        pageLength: 10,
        lengthChange: false,
        searching: false,
        info: false,
        columns: [
            { data: "asin", title: "ASIN" },
            { data: "sku",  title: "" }
        ],
        language: {
            paginate: {
                previous: "前へ",
                next: "次へ"
            },
            info: "全 _TOTAL_ 件中 _START_ から _END_ を表示",
            infoEmpty: "0 件中 0 から 0 を表示",
            emptyTable: "データがありません"
        }
    }); 

    // ✅ 一括登録ボタン（commitBtn）クリック処理（修正版）
    const commitBtn = document.getElementById("commitBtn");
    if (commitBtn) {
        commitBtn.addEventListener("click", async () => {
            const country_code = document.getElementById("globalRegion")?.value;
            // プルダウン未選択時は処理しない
            if (!country_code) return;
            
            const table = $("#csvOkTable").DataTable();
            const data = table.rows().data().toArray();

            if (!data.length) {
                window.showToast("登録可能なASINがありません", "error");
                return;
            }

            const asinList = data.map(row => row.asin).filter(a => a);
            const skuList  = data.map(row => row.sku || "").filter(s => s);

            if (!asinList.length) {
                window.showToast("ASINデータが見つかりません", "error");
                return;
            }

            window.showToast(`${asinList.length}件のASINを登録中...`, "info");

            try {
                const formData = new FormData();
                formData.append("country_code", country_code);
                formData.append("mode", "commit");

                asinList.forEach((asin, i) => {
                    formData.append("asins[]", asin);
                    formData.append("skus[]", skuList[i] || "");
                });

                const res = await fetch("/csv/csv_import", {
                    method: "POST",
                    body: formData
                });

                const result = await res.json();

                if (result.status === "success") {
                    window.showToast(`登録完了 (${asinList.length}件)`, "success");
                    table.clear().draw();
                } else {
                    window.showToast("登録に失敗しました", "error");
                }
            } catch (err) {
                console.error("登録エラー:", err);
                window.showToast("通信エラーが発生しました", "error");
            }
        });
    }

    // ✅ リージョン切替イベント監視（csv_importタブのみ）
    document.addEventListener("zsss:regionChanged", (e) => {
        const activeTab = document.querySelector(".sidebar-btn.active")?.getAttribute("data-target");
        if (activeTab !== "csv_import") return; // ← この1行を追加

        const newRegion = e.detail.region;
    });

    // ✅ CSV Export（ZSSS登録ASIN一括CSV出力）
    document.getElementById("exportListedCsvBtn").addEventListener("click", function() {
        const countryCode = document.getElementById("globalRegion").value;
        window.location.href = `/csv/export_listed_csv?country_code=${countryCode}`;
    });

    // ✅ 他社ツール出品済みASIN取込（重複出品防止・一時運用）
    const externalListedFileInput = document.getElementById("externalListedFileInput");
    const externalListedFileName = document.getElementById("externalListedFileName");
    const externalListedUploadBtn = document.getElementById("externalListedUploadBtn");
    const externalListedResult = document.getElementById("externalListedResult");

    if (externalListedFileName) {
        externalListedFileName.addEventListener("click", () => {
            externalListedFileInput.click();
        });
    }

    if (externalListedFileInput) {
        externalListedFileInput.addEventListener("change", (e) => {
            const fileName = e.target.files.length ? e.target.files[0].name : "";
            externalListedFileName.value = fileName;
        });
    }

    if (externalListedUploadBtn) {
        externalListedUploadBtn.addEventListener("click", () => {
            if (!externalListedFileInput.files.length) {
                alert("CSVファイルを選択してください");
                return;
            }

            const formData = new FormData();
            formData.append("file", externalListedFileInput.files[0]);
            formData.append("country_code", document.getElementById("globalRegion").value);

            if (externalListedResult) externalListedResult.textContent = "";

            fetch("/csv/external_listed_import", {
                method: "POST",
                body: formData
            })
            .then(response => response.json())
            .then(data => {
                if (data.status === "success") {
                    const msg = `取込完了：${data.import}件追加（合計${data.after}件）`;
                    if (externalListedResult) externalListedResult.textContent = msg;
                    window.showToast(msg, "success");
                    externalListedFileInput.value = "";
                    externalListedFileName.value = "";
                } else {
                    const errMsg = data && data.message ? data.message : "取込に失敗しました";
                    if (externalListedResult) externalListedResult.textContent = errMsg;
                    window.showToast(errMsg, "error");
                }
            })
            .catch(err => {
                console.error("[External Listed ASIN Import] error:", err);
                window.showToast("エラーが発生しました", "error");
            });
        });
    }

});

