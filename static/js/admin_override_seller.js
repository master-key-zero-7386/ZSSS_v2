// =====================================================
// ファイル名: static/js/admin_override_seller.js
// 目的：別途送料誤判定セラー管理JS
// =====================================================

// --- ▼ SECTION 01: ▼ ---
document.addEventListener("DOMContentLoaded", () => {

    console.log("override js loaded");

    window.overrideSellerTable = $('#override-seller-table').DataTable({

        autoWidth: false,

        ajax: {
            url: "/override_seller/list",
            type: "POST",
            contentType: "application/json",

            data: function () {
                return JSON.stringify({
                    country_code: window.getCurrentRegion()
                });
            },

            dataSrc: "data"
        },

        columns: [
            { data: null, render: (d, t, r, m) => m.row + 1 },
            { data: "seller_id" },
            { data: "seller_name" },
            { data: "shipping_amount" },
            { data: "remarks" },
            {
                data: null,
                orderable: false,
                searchable: false,
                render: function () {
                    return `
                        <button class="btn-blue btn-override-edit">編集</button>
                        <button class="btn-red btn-override-delete">削除</button>
                    `;
                }
            }
        ],

        paging: false,
        searching: false,
        info: false
    });
});

$(document)
.off("change", "#globalRegion")
.on("change", "#globalRegion", function () {

    window.overrideSellerTable.ajax.reload(null, true);

});

// --- ▼ SECTION 02: 新規追加 ▼ ---
$(document)
.off("click", "#btn-add-override-seller")
.on("click", "#btn-add-override-seller", function () {

    if ($("#override-seller-table tr.editing").length > 0) {
        alert("編集中の行があります");
        return;
    }

    const row = window.overrideSellerTable.row.add({
        seller_id: "",
        seller_name: "",
        shipping_amount: "",
        remarks: ""
    }).draw(false);

    const $tr = $(row.node());

    $tr.addClass("editing new-row");

    $tr.find("td:eq(1)").html(`<input class="edit-seller_id">`);
    $tr.find("td:eq(2)").html(`<input class="edit-seller_name">`);
    $tr.find("td:eq(3)").html(`<input class="edit-shipping_amount">`);
    $tr.find("td:eq(4)").html(`<input class="edit-remarks">`);

    $tr.find("td:last").html(`
        <button class="btn-blue btn-override-save">保存</button>
        <button class="btn-override-cancel">キャンセル</button>
    `);
});

// --- ▼ SECTION 03: 保存 ▼ ---
$(document)
.off("click", ".btn-override-save")
.on("click", ".btn-override-save", function () {

    const $tr = $(this).closest("tr");

    fetch("/override_seller/insert", {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({
            country_code: window.getCurrentRegion(),
            seller_id: $tr.find(".edit-seller_id").val(),
            seller_name: $tr.find(".edit-seller_name").val(),
            shipping_amount: $tr.find(".edit-shipping_amount").val(),
            remarks: $tr.find(".edit-remarks").val()
        })
    })
    .then(r => r.json())
    .then(res => {
        if (res.status !== "ok") return alert("失敗");
        window.overrideSellerTable.ajax.reload(null, false);
    });
});

// --- ▼ SECTION 04: キャンセル ▼ ---
$(document)
.off("click", ".btn-override-cancel")
.on("click", ".btn-override-cancel", function () {
    window.overrideSellerTable.ajax.reload(null, false);
});

// --- ▼ SECTION 05: 編集 ▼ ---
$(document)
.off("click", ".btn-override-edit")
.on("click", ".btn-override-edit", function () {

    const $tr = $(this).closest("tr");

    if ($("#override-seller-table tr.editing").length > 0) {
        alert("編集中の行があります");
        return;
    }

    const data = window.overrideSellerTable.row($tr).data();

    $tr.addClass("editing");

    $tr.find("td:eq(1)").html(`<input class="edit-seller_id" value="${data.seller_id}">`);
    $tr.find("td:eq(2)").html(`<input class="edit-seller_name" value="${data.seller_name}">`);
    $tr.find("td:eq(3)").html(`<input class="edit-shipping_amount" value="${data.shipping_amount}">`);
    $tr.find("td:eq(4)").html(`<input class="edit-remarks" value="${data.remarks || ""}">`);

    $tr.find("td:last").html(`
        <button class="btn-blue btn-override-update">保存</button>
        <button class="btn-override-cancel-edit">キャンセル</button>
    `);
});

// --- ▼ SECTION 06: 更新 ▼ ---
$(document)
.off("click", ".btn-override-update")
.on("click", ".btn-override-update", function () {

    const $tr = $(this).closest("tr");

    fetch("/override_seller/update", {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({
            country_code: window.getCurrentRegion(),
            seller_id: $tr.find(".edit-seller_id").val(),
            seller_name: $tr.find(".edit-seller_name").val(),
            shipping_amount: $tr.find(".edit-shipping_amount").val(),
            remarks: $tr.find(".edit-remarks").val()
        })
    })
    .then(r => r.json())
    .then(res => {
        if (res.status !== "ok") return alert("失敗");
        window.overrideSellerTable.ajax.reload(null, false);
    });
});

// --- ▼ SECTION 07: 編集キャンセル ▼ ---
$(document)
.off("click", ".btn-override-cancel-edit")
.on("click", ".btn-override-cancel-edit", function () {
    window.overrideSellerTable.ajax.reload(null, false);
});

// --- ▼ SECTION 08: 削除 ▼ ---
$(document)
.off("click", ".btn-override-delete")
.on("click", ".btn-override-delete", function () {

    const $tr = $(this).closest("tr");
    const data = window.overrideSellerTable.row($tr).data();

    if (!confirm("削除しますか？")) return;

    fetch("/override_seller/delete", {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({
            country_code: window.getCurrentRegion(),
            seller_id: data.seller_id
        })
    })
    .then(r => r.json())
    .then(res => {
        if (res.status !== "ok") return alert("失敗");
        window.overrideSellerTable.ajax.reload(null, false);
    });
});