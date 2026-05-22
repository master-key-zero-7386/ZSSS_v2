// =====================================================
// ファイル名: static/js/admin_marketplace_master.js
// 目的: marketplaces_master 管理画面 UI制御
// =====================================================

// --- ▼ SECTIONⅠ : Marketplaces Master ▼ ---
function initMarketplaceMaster() {
    // --- ▼ SECTIONⅠ 01: 初期ロード ▼ ---
    if ($.fn.DataTable.isDataTable('#mkt-master-table')) {
        $('#mkt-master-table').DataTable().destroy();
    }

    window.mktTable = $('#mkt-master-table').DataTable({
        // scrollX: true,
        // scrollY: '40vh',
        // scrollCollapse: true, 
        autoWidth: false,

        ajax: {
            url: '/account/admin/get_marketplaces_master',
            dataSrc: 'data' 
        },
        columns: [
            { data: null, render: (d, t, r, m) => m.row + 1 },
            { data: 'country_code' },
            { data: 'display_name' },
            { data: 'marketplace_id' },
            { data: 'currency' },
            { data: 'weight_unit' },
            { data: 'dimension_unit' },

            { data: 'locale' },
            { data: 'override_exchange_rate' },
            { data: 'timezone' },
            { data: 'tax_mode' },

            { data: 'host' },
            { data: 'spapi_host' },            
            {
                data: null,
                render: () => `<button class="btn-blue btn-mkt-edit">編集</button>`
            }
        ],
        paging: false,
        searching: false,
        info: false
    });

    // --- ▼ SECTIONⅠ 02: 新規追加ボタン ▼ ---
    $(document)
    .off('click', '#btn-add-marketplace')
    .on('click', '#btn-add-marketplace', function () {
        // すでに編集中の行があれば止める
        if ($('#mkt-master-table tr.editing').length > 0) {
            alert('編集中の行があります');
            return;
        }

        // 空行データ
        const emptyRow = {
            country_code: '',
            display_name: '',
            marketplace_id: '',
            currency: '',
            weight_unit: '',
            dimension_unit: '',

            locale: '',
            override_exchange_rate: '',
            timezone: '',
            tax_mode: '',

            host: '',
            spapi_host: ''         
        };

        // DataTable に1行追加
        const row = window.mktTable.row.add(emptyRow).draw(false);
        const $tr = $(row.node());

        // ★ 新規行マーク（INSERT判定の要）
        $tr.addClass('editing new-row');
        $tr.data('originalRowData', null);

        // ★ 新規行は最初から input 化する
        const editableColumns = [
        { index: 1, key: 'country_code', type: 'text', width: 50 },
        { index: 2, key: 'display_name', type: 'text', width: 80 },
        { index: 3, key: 'marketplace_id', type: 'text', width: 160 },
        { index: 4, key: 'currency', type: 'text', width: 60 },
        { index: 5, key: 'weight_unit', type: 'text', width: 60 },
        { index: 6, key: 'dimension_unit', type: 'text', width: 60 },

        { index: 7, key: 'locale', type: 'text', width: 80 },
        { index: 8, key: 'override_exchange_rate', type: 'number', width: 50 },
        { index: 9, key: 'timezone', type: 'text', width: 140 },
        { index: 10, key: 'tax_mode', type: 'text', width: 60 },        

        { index: 11, key: 'host', type: 'text', width: 200 },
        { index: 12, key: 'spapi_host', type: 'text', width: 240 }      
        ];

        // ★ 全カラムを即 input 化
        editableColumns.forEach(col => {
        $tr.find(`td:eq(${col.index})`).html(
            `<input type="${col.type}"
                    class="edit-${col.key}"
                    value=""
                    style="width:${col.width}px;">`
        );
        });

        // 保存・キャンセルを出す
        $tr.find('td:last').html(`
        <button class="btn-blue btn-mkt-save">保存</button>
        <button class="btn-mkt-cancel">キャンセル</button>
        `);

        // ★ 詳細行（client系4項目）を新規追加でも表示
        const rowApi = window.mktTable.row($tr);

        if (rowApi.child.isShown()) {
            rowApi.child.hide();
        }

        const detailHtml = `
        <div class="mkt-detail-box">
            <div class="mkt-detail-row">
                <label>client_id</label>
                <input type="text" class="edit-client_id" value="" style="width:1400px;">
            </div>
            <div class="mkt-detail-row">
                <label>client_secret</label>
                <input type="text" class="edit-client_secret" value="" style="width:1400px;">
            </div>
            <div class="mkt-detail-row">
                <label>access_key</label>
                <input type="text" class="edit-access_key" value="" style="width:1400px;">
            </div>
            <div class="mkt-detail-row">
                <label>secret_key</label>
                <input type="text" class="edit-secret_key" value="" style="width:1400px;">
            </div>
        </div>
        `;

        rowApi.child(detailHtml).show();        

    });

    // --- ▼ SECTIONⅠ 03: インライン編集（全カラム編集対応） ▼ ---
    $('#mkt-master-table')
    .off('click', '.btn-mkt-edit')
    .on('click', '.btn-mkt-edit', function () {

        const $tr = $(this).closest('tr');

        // 二重編集防止
        if ($tr.hasClass('editing')) return;

        const rowData = window.mktTable.row($tr).data();
        console.log("ROW DATA >>>", rowData); // チェック完了後削除

        // ★ キャンセル用に元データ退避
        $tr.data('originalRowData', { ...rowData });
        $tr.addClass('editing');

        // ★ 編集対象カラム定義（marketplace_id は除外）
        const editableColumns = [
        { index: 1, key: 'country_code', type: 'text', width: 50 },
        { index: 2, key: 'display_name', type: 'text', width: 80 },
        { index: 3, key: 'marketplace_id', type: 'text', width: 160 },
        { index: 4, key: 'currency', type: 'text', width: 60 },
        { index: 5, key: 'weight_unit', type: 'text', width: 60 },
        { index: 6, key: 'dimension_unit', type: 'text', width: 60 },

        { index: 7, key: 'locale', type: 'text', width: 80 },
        { index: 8, key: 'override_exchange_rate', type: 'number', width: 50 },
        { index: 9, key: 'timezone', type: 'text', width: 140 },
        { index: 10, key: 'tax_mode', type: 'text', width: 60 },        

        { index: 11, key: 'host', type: 'text', width: 200 },
        { index: 12, key: 'spapi_host', type: 'text', width: 240 }     
        ];

        // ★ 全カラムを input 化
        editableColumns.forEach(col => {
        const value = rowData[col.key] ?? '';

        console.log("EDIT COL >>>", col.key, value, rowData); // チェック完了後削除    

        $tr.find(`td:eq(${col.index})`).html(
            `<input type="${col.type}"
                    class="edit-${col.key}"
                    value="${value}"
                    style="width:${col.width}px;">`
        );
        });

        // ★ 編集 → 保存＋キャンセル
        const $td = $(this).closest('td');
        $(this).hide();
        $td.append(`
        <button class="btn-blue btn-mkt-save">保存</button>
        <button class="btn-mkt-cancel">キャンセル</button>
        <button class="btn-mkt-delete">削除</button>
        `);

        // ★ 詳細行（client系4項目）を表示
        const row = window.mktTable.row($tr);

        // 既に開いていたら一旦閉じる（安全策）
        if (row.child.isShown()) {
            row.child.hide();
        }

        // 詳細HTML（縦並び）
        const detailHtml = `
        <div class="mkt-detail-box">
            <div class="mkt-detail-row">
                <label>client_id</label>
                <input type="text" class="edit-client_id"
                    value="${rowData.client_id ?? ''}" style="width:1400px;">
            </div>
            <div class="mkt-detail-row">
                <label>client_secret</label>
                <input type="text" class="edit-client_secret"
                    value="${rowData.client_secret ?? ''}" style="width:1400px;">
            </div>
            <div class="mkt-detail-row">
                <label>access_key</label>
                <input type="text" class="edit-access_key"
                    value="${rowData.access_key ?? ''}" style="width:1400px;">
            </div>
            <div class="mkt-detail-row">
                <label>secret_key</label>
                <input type="text" class="edit-secret_key"
                    value="${rowData.secret_key ?? ''}" style="width:1400px;">
            </div>
        </div>
        `;

        // 表示
        row.child(detailHtml).show();

    });

    // --- ▼ SECTIONⅠ 04: 編集アクションボタン制御 ▼ ---
    $('#mkt-master-table')
    .on('click', '.btn-mkt-cancel', function () {
        const $td = $(this).closest('td');
        const $tr = $td.closest('tr');

        // ① 操作ボタン削除・編集ボタン復帰
        $td.find('.btn-mkt-save, .btn-mkt-cancel, .btn-mkt-delete').remove();
        $td.find('.btn-mkt-edit').show();
        $tr.removeClass('editing');

        // ② 元データを復元
        const original = $tr.data('originalRowData');
        if (original) {
            const row = window.mktTable.row($tr);
            row.data(original).draw(false);
        }

        // ③ 詳細行を閉じる
        const row = window.mktTable.row($tr);
        if (row.child.isShown()) {
            row.child.hide();
        }
    });

    // --- ▼ SECTIONⅠ 05: 保存処理（INSERT / UPDATE 分岐） ▼ ---
    $('#mkt-master-table')
    .off('click', '.btn-mkt-save')
    .on('click', '.btn-mkt-save', function () {

        const $tr = $(this).closest('tr');
        const original = $tr.data('originalRowData'); // null → 新規


        console.log("SAVE HTML >>>", $tr.html()); // チェック完了後削除

        // ★ 入力値回収（全カラム）
        const payload = {
            marketplace_id: original ? original.marketplace_id : $tr.find('.edit-marketplace_id').val(),

            country_code: $tr.find('.edit-country_code').val(),
            display_name: $tr.find('.edit-display_name').val(),
            currency: $tr.find('.edit-currency').val(),
            weight_unit: $tr.find('.edit-weight_unit').val(),
            dimension_unit: $tr.find('.edit-dimension_unit').val(),

            locale: $tr.find('.edit-locale').val(),
            override_exchange_rate: $tr.find('.edit-override_exchange_rate').val(),
            timezone: $tr.find('.edit-timezone').val(),
            tax_mode: $tr.find('.edit-tax_mode').val(),

            host: $tr.find('.edit-host').val(),
            spapi_host: $tr.find('.edit-spapi_host').val(),            
  
            client_id: $('.edit-client_id').val(), 
            client_secret: $('.edit-client_secret').val(), 
            access_key: $('.edit-access_key').val(), 
            secret_key: $('.edit-secret_key').val()     

        };

        // ★ 分岐：新規 or 更新
        const url = original
            ? '/admin/marketplace_master/update'
            : '/admin/marketplace_master/insert';

        console.log("PAYLOAD >>>", payload); // チェック完了後削除

        fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        })
        .then(r => r.json())
        .then(res => {
            if (res.status !== 'ok') {
                alert(res.message || '保存に失敗しました');
                return;
            }

            // INSERT時：返却された marketplace_id を反映
            if (!original && res.marketplace_id) {
                payload.marketplace_id = res.marketplace_id;
            }

            // ★ DataTable 内部データ更新
            const row = window.mktTable.row($tr);
            const rowData = row.data();
            Object.assign(rowData, payload);

            row.data(rowData).invalidate().draw(false);

            // ★ 編集状態解除
            $tr.find('.btn-mkt-save, .btn-mkt-cancel').remove();
            $tr.find('td:last').html('<button class="btn-blue btn-mkt-edit">編集</button>');

            if (row.child.isShown()) {
                row.child.hide();
            }
            
            $tr.removeClass('editing new-row');
            $tr.removeData('originalRowData');
        })
        .catch(() => {
            alert('通信エラーが発生しました');
        });
    });

    // --- ▼ SECTIONⅠ 06: キャンセル処理（全カラム復元） ▼ ---
    $('#mkt-master-table')
    .off('click', '.btn-mkt-cancel')
    .on('click', '.btn-mkt-cancel', function () {

        const $tr = $(this).closest('tr');
        const original = $tr.data('originalRowData');
        const row = window.mktTable.row($tr);

        // ===== ▼ 新規追加行のキャンセル ▼ =====
        if (!original) {
            // 詳細行を閉じる
            if (row.child && row.child.isShown()) {
                row.child.hide();
            }

            // 行そのものを削除
            row.remove().draw(false);

            return;
        }

        // ★ 元データを全カラム復元
        $tr.find('td:eq(1)').text(original.country_code);        
        $tr.find('td:eq(2)').text(original.display_name);
        $tr.find('td:eq(3)').text(original.marketplace_id);
        $tr.find('td:eq(4)').text(original.currency);
        $tr.find('td:eq(5)').text(original.weight_unit);
        $tr.find('td:eq(6)').text(original.dimension_unit);

        $tr.find('td:eq(7)').text(original.locale);
        $tr.find('td:eq(8)').text(original.override_exchange_rate);
        $tr.find('td:eq(9)').text(original.timezone);
        $tr.find('td:eq(10)').text(original.tax_mode); 
        
        $tr.find('td:eq(11)').text(original.host);
        $tr.find('td:eq(12)').text(original.spapi_host);        

        // ボタン復元
        $tr.find('.btn-mkt-save, .btn-mkt-cancel').remove();
        $tr.find('td:last').html('<button class="btn-blue btn-mkt-edit">編集</button>');

        $tr.removeClass('editing');
        $tr.removeData('originalRowData');

        // ★ 詳細行を閉じる
        if (row.child && row.child.isShown()) {
            row.child.hide();
        }        

    });

    // --- ▼ SECTIONⅠ 07: 削除処理（確認 → DELETE） ▼ ---
    $('#mkt-master-table')
    .off('click', '.btn-mkt-delete')
    .on('click', '.btn-mkt-delete', function () {

        const $tr = $(this).closest('tr');
        const row = window.mktTable.row($tr);
        const rowData = row.data();

        if (!rowData || !rowData.marketplace_id) {
            alert('削除対象が特定できません');
            return;
        }

        // 確認
        if (!confirm(`このマーケットプレイスを削除します。\n\nmarketplace_id: ${rowData.marketplace_id}\n\nよろしいですか？`)) {
            return;
        }

        fetch('/admin/marketplace_master/delete', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                marketplace_id: rowData.marketplace_id
            })
        })
        .then(r => r.json())
        .then(res => {
            if (res.status !== 'ok') {
                alert(res.message || '削除に失敗しました');
                return;
            }

            // child 行を閉じる
            if (row.child && row.child.isShown()) {
                row.child.hide();
            }

            // 行削除
            row.remove().draw(false);
        })
        .catch(() => {
            alert('通信エラーが発生しました');
        });
    });
}

// --- ▼ SECTIONⅡ : Amazon ID ▼ ---
function initAmazonRetail() {
    // --- ▼ SECTIONⅡ 01: 初期ロード ▼ ---
    if ($.fn.DataTable.isDataTable('#amazon-retail-table')) {
        $('#amazon-retail-table').DataTable().destroy();
    }

    window.amazonRetailTable = $('#amazon-retail-table').DataTable({
        // scrollX: true,
        // scrollY: '40vh',
        // scrollCollapse: true, 
        autoWidth: false,

        ajax: {
            url: '/account/admin/get_amazon_retail',
            dataSrc: 'data' 
        },
        columns: [
            { data: null, render: (d,t,r,m)=>m.row+1 },
            { data: 'country_code' },
            { data: 'seller_id' },
            { data: 'note' },
            {
                data: null,
                render: () => `<button class="btn-blue btn-mkt-edit">編集</button>`
            }
        ],
        paging: false,
        searching: false,
        info: false
    });

    // --- ▼ SECTIONⅡ 02: 新規追加ボタン ▼ ---
    $(document)
    .off('click', '#btn-add-amazon-seller')
    .on('click', '#btn-add-amazon-seller', function () {
        // すでに編集中の行があれば止める
        if ($('#amazon-retail-table tr.editing').length > 0) {
            alert('編集中の行があります');
            return;
        }

        // 空行データ
        const emptyRow = {
            country_code: '',
            seller_id: '',
            note: ''
        };        

        // DataTable に1行追加
        const row = window.amazonRetailTable.row.add(emptyRow).draw(false);
        const $tr = $(row.node());

        // ★ 新規行マーク（INSERT判定の要）
        $tr.addClass('editing new-row');
        $tr.data('originalRowData', null);

        // ★ 新規行は最初から input 化する
        const editableColumns = [
        { index: 1, key: 'country_code', type: 'text', width: 60 },
        { index: 2, key: 'seller_id', type: 'text', width: 200 },
        { index: 3, key: 'note', type: 'text', width: 200 }            
        ];

        // ★ 全カラムを即 input 化
        editableColumns.forEach(col => {
        $tr.find(`td:eq(${col.index})`).html(
            `<input type="${col.type}"
                    class="edit-${col.key}"
                    value=""
                    style="width:${col.width}px;">`
        );
        });

        // 保存・キャンセルを出す
        $tr.find('td:last').html(`
        <button class="btn-blue btn-mkt-save">保存</button>
        <button class="btn-mkt-cancel">キャンセル</button>
        `);
    });

    // --- ▼ SECTIONⅡ 03: インライン編集（全カラム編集対応） ▼ ---
    $('#amazon-retail-table')
    .off('click', '.btn-mkt-edit')
    .on('click', '.btn-mkt-edit', function () {

        const $tr = $(this).closest('tr');

        // 二重編集防止
        if ($tr.hasClass('editing')) return;

        const rowData = window.amazonRetailTable.row($tr).data();

        // ★ キャンセル用に元データ退避
        $tr.data('originalRowData', { ...rowData });
        $tr.addClass('editing');

        //
        const editableColumns = [
        { index: 1, key: 'country_code', type: 'text', width: 60 },
        { index: 2, key: 'seller_id', type: 'text', width: 200 },
        { index: 3, key: 'note', type: 'text', width: 200 }
        ];

        // ★ 全カラムを input 化
        editableColumns.forEach(col => {
        const value = rowData[col.key] ?? '';
        $tr.find(`td:eq(${col.index})`).html(
            `<input type="${col.type}"
                    class="edit-${col.key}"
                    value="${value}"
                    style="width:${col.width}px;">`
        );
        });

        // ★ 編集 → 保存＋キャンセル
        const $td = $(this).closest('td');
        $(this).hide();
        $td.append(`
        <button class="btn-blue btn-mkt-save">保存</button>
        <button class="btn-mkt-cancel">キャンセル</button>
        <button class="btn-mkt-delete">削除</button>
        `);
    });

    // --- ▼ SECTIONⅡ 04: 編集アクションボタン制御 ▼ ---
    $('#amazon-retail-table')
    .on('click', '.btn-mkt-cancel', function () {
        const $td = $(this).closest('td');
        const $tr = $td.closest('tr');

        // ① 操作ボタン削除・編集ボタン復帰
        $td.find('.btn-mkt-save, .btn-mkt-cancel, .btn-mkt-delete').remove();
        $td.find('.btn-mkt-edit').show();
        $tr.removeClass('editing');

        // ② 元データを復元
        const original = $tr.data('originalRowData');
        if (original) {
            const row = window.amazonRetailTable.row($tr);
            row.data(original).draw(false);
        }
    });

    // --- ▼ SECTIONⅡ 05: 保存処理（INSERT / UPDATE 分岐） ▼ ---
    $('#amazon-retail-table')
    .off('click', '.btn-mkt-save')
    .on('click', '.btn-mkt-save', function () {

        const $tr = $(this).closest('tr');
        const original = $tr.data('originalRowData'); // null → 新規

        // ★ 入力値回収（全カラム）
        const payload = {
            country_code: $tr.find('.edit-country_code').val(),
            seller_id: $tr.find('.edit-seller_id').val(),
            note: $tr.find('.edit-note').val()     
        };

        // ★ 分岐：新規 or 更新
        const url = original
            ? '/admin/amazon_retail/update'
            : '/admin/amazon_retail/insert';

        fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        })
        .then(r => r.json())
        .then(res => {
            if (res.status !== 'ok') {
                alert(res.message || '保存に失敗しました');
                return;
            }

            // INSERT時：返却された seller_id を反映
            if (!original && res.seller_id) {
                payload.seller_id = res.seller_id;
            }

            // ★ DataTable 内部データ更新
            const row = window.amazonRetailTable.row($tr);
            const rowData = row.data();
            Object.assign(rowData, payload);

            row.data(rowData).invalidate().draw(false);

            // ★ 編集状態解除
            $tr.find('.btn-mkt-save, .btn-mkt-cancel').remove();
            $tr.find('td:last').html('<button class="btn-blue btn-mkt-edit">編集</button>');

            $tr.removeClass('editing new-row');
            $tr.removeData('originalRowData');
        })
        .catch(() => {
            alert('通信エラーが発生しました');
        });
    });

    // --- ▼ SECTIONⅡ 06: キャンセル処理（全カラム復元） ▼ ---
    $('#amazon-retail-table')
    .off('click', '.btn-mkt-cancel')
    .on('click', '.btn-mkt-cancel', function () {

        const $tr = $(this).closest('tr');
        const original = $tr.data('originalRowData');
        const row = window.amazonRetailTable.row($tr);

        // ===== ▼ 新規追加行のキャンセル ▼ =====
        if (!original) {
            // 行そのものを削除
            row.remove().draw(false);

            return;
        }

        // ★ 元データを全カラム復元
        $tr.find('td:eq(1)').text(original.country_code);
        $tr.find('td:eq(2)').text(original.seller_id);
        $tr.find('td:eq(3)').text(original.note); 

        // ボタン復元
        $tr.find('.btn-mkt-save, .btn-mkt-cancel').remove();
        $tr.find('td:last').html('<button class="btn-blue btn-mkt-edit">編集</button>');

        $tr.removeClass('editing');
        $tr.removeData('originalRowData');
    });

    // --- ▼ SECTIONⅡ 07: 削除処理（確認 → DELETE） ▼ ---
    $('#amazon-retail-table')
    .off('click', '.btn-mkt-delete')
    .on('click', '.btn-mkt-delete', function () {

        const $tr = $(this).closest('tr');
        const row = window.amazonRetailTable.row($tr);
        const rowData = row.data();

        if (!rowData || !rowData.seller_id)  {
            alert('削除対象が特定できません');
            return;
        }

        // 確認
        if (!confirm(`このマーケットプレイスを削除します。\n\nseller_id: ${rowData.seller_id}\n\nよろしいですか？`)) {
            return;
        }

        fetch('/admin/amazon_retail/delete',  {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                seller_id: rowData.seller_id
            })
        })
        .then(r => r.json())
        .then(res => {
            if (res.status !== 'ok') {
                alert(res.message || '削除に失敗しました');
                return;
            }

            // 行削除
            row.remove().draw(false);
        })
        .catch(() => {
            alert('通信エラーが発生しました');
        });
    });

}

document.addEventListener("DOMContentLoaded", function () {
    initMarketplaceMaster();
    initAmazonRetail(); 
});


