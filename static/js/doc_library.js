// ==========================================
// ファイル名: static/js/doc_library.js
// 目的: その他ツール「文書管理」（購入者メッセージ等の定型文）
//       カテゴリ → 文書一覧 → 本文表示・コピー／編集。インポート・エクスポートはJSON。
// ==========================================
document.addEventListener("DOMContentLoaded", () => {
    const root = document.getElementById("st-doclibrary");
    if (!root) return;

    const API = "/tools/doc_library";
    const ALL = "all";

    const state = {
        categories: [],
        templates: [],
        selectedCategory: ALL,   // "all" またはカテゴリid
        selectedTemplateId: null,
        editingId: null,         // 編集中の文書id（新規はnull）
        loaded: false,
    };

    const $ = id => document.getElementById(id);

    function setStatus(message, isError = false) {
        const el = $("dlStatus");
        el.textContent = message || "";
        el.style.color = isError ? "red" : "green";
    }

    async function postJson(path, body) {
        const resp = await fetch(API + path, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
        });
        const result = await resp.json().catch(() => ({}));
        if (!resp.ok || result.status !== "ok") {
            throw new Error(result.message || "処理に失敗しました。");
        }
        return result;
    }

    // --- ▼ データ読込 ---
    async function load() {
        try {
            const resp = await fetch(API + "/data");
            const result = await resp.json();
            if (!resp.ok || result.status !== "ok") throw new Error(result.message || "読み込みに失敗しました。");
            state.categories = result.categories || [];
            state.templates = result.templates || [];
            state.loaded = true;

            if (state.selectedCategory !== ALL &&
                !state.categories.some(c => c.id === state.selectedCategory)) {
                state.selectedCategory = ALL;
            }
            if (!state.templates.some(t => t.id === state.selectedTemplateId)) {
                state.selectedTemplateId = null;
            }
            renderAll();
        } catch (e) {
            console.error("doc_library load error:", e);
            setStatus(e.message, true);
        }
    }

    function categoryName(id) {
        return (state.categories.find(c => c.id === id) || {}).name || "";
    }

    function renderAll() {
        renderCategories();
        renderTemplates();
        renderView();
    }

    // --- ▼ 左：カテゴリ ---
    function renderCategories() {
        const ul = $("dlCategoryList");
        ul.innerHTML = "";

        const makeItem = (id, name, count) => {
            const li = document.createElement("li");
            if (state.selectedCategory === id) li.classList.add("active");

            const nameEl = document.createElement("span");
            nameEl.className = "dl-name";
            nameEl.textContent = name;
            li.appendChild(nameEl);

            const countEl = document.createElement("span");
            countEl.className = "dl-count";
            countEl.textContent = `(${count})`;
            li.appendChild(countEl);

            li.addEventListener("click", () => {
                state.selectedCategory = id;
                renderCategories();
                renderTemplates();
            });
            ul.appendChild(li);
            return li;
        };

        makeItem(ALL, "すべて", state.templates.length);

        state.categories.forEach((c, idx) => {
            const count = state.templates.filter(t => t.category_id === c.id).length;
            const li = makeItem(c.id, c.name, count);

            const addBtn = (label, title, handler) => {
                const b = document.createElement("button");
                b.type = "button";
                b.className = "dl-mini-btn";
                b.textContent = label;
                b.title = title;
                b.addEventListener("click", ev => { ev.stopPropagation(); handler(); });
                li.appendChild(b);
            };
            if (idx > 0) addBtn("▲", "上へ", () => moveCategory(c.id, "up"));
            if (idx < state.categories.length - 1) addBtn("▼", "下へ", () => moveCategory(c.id, "down"));
            addBtn("✎", "名前を変更", () => renameCategory(c));
            addBtn("×", "削除", () => deleteCategory(c, count));
        });

        if (!state.categories.length) {
            const li = document.createElement("li");
            li.className = "dl-empty";
            li.style.cursor = "default";
            li.textContent = "まず「＋ カテゴリ追加」でカテゴリを作ってください。";
            ul.appendChild(li);
        }
    }

    async function addCategory() {
        const name = (prompt("新しいカテゴリ名") || "").trim();
        if (!name) return;
        try {
            const result = await postJson("/category/save", { name });
            state.selectedCategory = result.id;
            setStatus(`カテゴリ「${name}」を追加しました。`);
            await load();
        } catch (e) {
            setStatus(e.message, true);
        }
    }

    async function renameCategory(c) {
        const name = (prompt("カテゴリ名を変更", c.name) || "").trim();
        if (!name || name === c.name) return;
        try {
            await postJson("/category/save", { id: c.id, name });
            setStatus(`カテゴリ名を「${name}」に変更しました。`);
            await load();
        } catch (e) {
            setStatus(e.message, true);
        }
    }

    async function deleteCategory(c, count) {
        if (count) {
            setStatus(`「${c.name}」には文書が${count}件入っているので削除できません。先に文書を削除するか、別のカテゴリへ移してください。`, true);
            return;
        }
        if (!confirm(`カテゴリ「${c.name}」を削除します。よろしいですか？`)) return;
        try {
            await postJson("/category/delete", { id: c.id });
            setStatus(`カテゴリ「${c.name}」を削除しました。`);
            await load();
        } catch (e) {
            setStatus(e.message, true);
        }
    }

    async function moveCategory(id, direction) {
        try {
            await postJson("/category/move", { id, direction });
            await load();
        } catch (e) {
            setStatus(e.message, true);
        }
    }

    // --- ▼ 中：文書一覧（カテゴリ＋検索で絞り込み） ---
    function filteredTemplates() {
        const q = ($("dlSearch").value || "").trim().toLowerCase();
        return state.templates.filter(t => {
            if (state.selectedCategory !== ALL && t.category_id !== state.selectedCategory) return false;
            if (!q) return true;
            return (t.title || "").toLowerCase().includes(q) || (t.body || "").toLowerCase().includes(q);
        });
    }

    function renderTemplates() {
        const ul = $("dlTemplateList");
        ul.innerHTML = "";

        const list = filteredTemplates();
        $("dlListTitle").textContent = state.selectedCategory === ALL
            ? `文書（${list.length}件）`
            : `${categoryName(state.selectedCategory)}（${list.length}件）`;

        list.forEach(t => {
            const li = document.createElement("li");
            if (t.id === state.selectedTemplateId) li.classList.add("active");

            const nameEl = document.createElement("span");
            nameEl.className = "dl-name";
            nameEl.textContent = t.title;
            if (state.selectedCategory === ALL) {
                const sub = document.createElement("span");
                sub.className = "dl-sub";
                sub.textContent = categoryName(t.category_id);
                nameEl.appendChild(sub);
            }
            li.appendChild(nameEl);

            li.addEventListener("click", () => {
                if ($("dlEdit").style.display !== "none" &&
                    !confirm("編集中の内容は保存されません。よろしいですか？")) return;
                state.selectedTemplateId = t.id;
                state.editingId = null;
                showMode("view");
                renderTemplates();
                renderView();
            });
            ul.appendChild(li);
        });

        if (!list.length) {
            const li = document.createElement("li");
            li.className = "dl-empty";
            li.style.cursor = "default";
            li.textContent = state.loaded ? "該当する文書はありません。" : "読み込み中…";
            ul.appendChild(li);
        }
    }

    // --- ▼ 右：本文表示／編集 ---
    function showMode(mode) {
        $("dlViewEmpty").style.display = mode === "empty" ? "" : "none";
        $("dlView").style.display = mode === "view" ? "" : "none";
        $("dlEdit").style.display = mode === "edit" ? "" : "none";
    }

    function renderView() {
        if ($("dlEdit").style.display !== "none") return;  // 編集中はそのまま
        const t = state.templates.find(x => x.id === state.selectedTemplateId);
        if (!t) {
            showMode("empty");
            return;
        }
        $("dlViewTitle").textContent = t.title;
        $("dlViewCategory").textContent = `カテゴリ：${categoryName(t.category_id)}`;
        $("dlViewBody").textContent = t.body || "";
        $("dlCopyMsg").textContent = "";
        showMode("view");
    }

    function openEditor(template) {
        if (!state.categories.length) {
            setStatus("先に「＋ カテゴリ追加」でカテゴリを作ってください。", true);
            return;
        }
        state.editingId = template ? template.id : null;

        const sel = $("dlEditCategory");
        sel.innerHTML = "";
        state.categories.forEach(c => {
            const opt = document.createElement("option");
            opt.value = c.id;
            opt.textContent = c.name;
            sel.appendChild(opt);
        });
        const defaultCat = template
            ? template.category_id
            : (state.selectedCategory !== ALL ? state.selectedCategory : state.categories[0].id);
        sel.value = String(defaultCat);

        $("dlEditHeading").textContent = template ? "文書を編集" : "新しい文書";
        $("dlEditTitle").value = template ? template.title : "";
        $("dlEditBody").value = template ? (template.body || "") : "";
        showMode("edit");
        $("dlEditTitle").focus();
    }

    async function saveTemplate() {
        const payload = {
            id: state.editingId,
            category_id: Number($("dlEditCategory").value),
            title: $("dlEditTitle").value,
            body: $("dlEditBody").value,
        };
        try {
            const result = await postJson("/template/save", payload);
            state.selectedTemplateId = result.id;
            state.editingId = null;
            showMode("view");
            setStatus(`「${payload.title.trim()}」を保存しました。`);
            await load();
        } catch (e) {
            setStatus(e.message, true);
        }
    }

    function cancelEdit() {
        state.editingId = null;
        showMode("view");
        renderView();
    }

    async function deleteTemplate() {
        const t = state.templates.find(x => x.id === state.selectedTemplateId);
        if (!t) return;
        if (!confirm(`「${t.title}」を削除します。よろしいですか？`)) return;
        try {
            await postJson("/template/delete", { id: t.id });
            state.selectedTemplateId = null;
            setStatus(`「${t.title}」を削除しました。`);
            await load();
        } catch (e) {
            setStatus(e.message, true);
        }
    }

    // ★ 外出先から http://(運用PCのアドレス):5001 で開くと navigator.clipboard が使えない
    //   （https / localhost 限定の機能）ため、その場合は昔ながらの方法でコピーする
    async function copyBody() {
        const t = state.templates.find(x => x.id === state.selectedTemplateId);
        if (!t) return;
        const text = t.body || "";
        let ok = false;

        if (navigator.clipboard && window.isSecureContext) {
            try {
                await navigator.clipboard.writeText(text);
                ok = true;
            } catch (e) {
                ok = false;
            }
        }
        if (!ok) {
            const ta = document.createElement("textarea");
            ta.value = text;
            ta.setAttribute("readonly", "");
            ta.style.position = "fixed";
            ta.style.top = "-1000px";
            document.body.appendChild(ta);
            ta.select();
            try {
                ok = document.execCommand("copy");
            } catch (e) {
                ok = false;
            }
            ta.remove();
        }

        const msg = $("dlCopyMsg");
        msg.textContent = ok ? "コピーしました" : "コピーできませんでした。本文を選択して Ctrl+C でコピーしてください。";
        msg.style.color = ok ? "green" : "red";
        if (ok) setTimeout(() => { if (msg.textContent === "コピーしました") msg.textContent = ""; }, 2500);
    }

    // --- ▼ エクスポート／インポート ---
    async function exportJson() {
        try {
            const resp = await fetch(API + "/export");
            if (!resp.ok) throw new Error("HTTP " + resp.status);
            const blob = await resp.blob();
            const d = new Date();
            const ymd = `${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, "0")}${String(d.getDate()).padStart(2, "0")}`;
            const url = URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            a.download = `doc_templates_${ymd}.json`;
            document.body.appendChild(a);
            a.click();
            a.remove();
            URL.revokeObjectURL(url);
            setStatus("エクスポートしました。");
        } catch (e) {
            console.error("doc_library export error:", e);
            setStatus("エクスポートに失敗しました。", true);
        }
    }

    async function importJson(file) {
        if (!file) return;
        if (!confirm(`「${file.name}」を取り込みます。\n同じカテゴリ・同じタイトルの文書は上書きされます（それ以外は追加、削除はしません）。よろしいですか？`)) return;

        const fd = new FormData();
        fd.append("file", file);
        try {
            const resp = await fetch(API + "/import", { method: "POST", body: fd });
            const result = await resp.json().catch(() => ({}));
            if (!resp.ok || result.status !== "ok") throw new Error(result.message || "インポートに失敗しました。");
            setStatus(`インポートしました：追加 ${result.added}件、上書き ${result.updated}件、新しいカテゴリ ${result.new_categories}件`);
            await load();
        } catch (e) {
            console.error("doc_library import error:", e);
            setStatus(e.message, true);
        }
    }

    // --- ▼ イベント ---
    $("dlSearch").addEventListener("input", renderTemplates);
    $("dlNewBtn").addEventListener("click", () => openEditor(null));
    $("dlAddCategoryBtn").addEventListener("click", addCategory);
    $("dlCopyBtn").addEventListener("click", copyBody);
    $("dlEditBtn").addEventListener("click", () => {
        openEditor(state.templates.find(x => x.id === state.selectedTemplateId));
    });
    $("dlDeleteBtn").addEventListener("click", deleteTemplate);
    $("dlSaveBtn").addEventListener("click", saveTemplate);
    $("dlCancelBtn").addEventListener("click", cancelEdit);
    $("dlExportBtn").addEventListener("click", exportJson);
    $("dlImportBtn").addEventListener("click", () => $("dlImportFile").click());
    $("dlImportFile").addEventListener("change", ev => {
        const file = ev.target.files[0];
        ev.target.value = "";  // 同じファイルを続けて選んでも反応するように
        importJson(file);
    });

    // サブタブを開いた時に最新を読み込む（他PC・別タブでの変更を拾う）
    document.querySelector('.st-subtab-btn[data-target="st-doclibrary"]')
        ?.addEventListener("click", () => { if ($("dlEdit").style.display === "none") load(); });

    load();
});
