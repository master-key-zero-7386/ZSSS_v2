# ======================================================
# Copyright (c) 2026 ZSSS
# All Rights Reserved.
# ------------------------------------------------------
# # ファイル名: amazon/adapters/catalog_normalized_adapter.py
# 目的: raw_json　⇒　normalized
# ======================================================

class NormalizedCatalogAdapter:

    # --- ▼ SECTION 01: AmazonAdapter を保持（HOME/REGION共通） ▼ ---
    def __init__(self, parent_adapter):
        """
        HOME / REGION 共通で使用する normalized adapter の基盤。
        """
        self.parent = parent_adapter

    # --- ▼ SECTION 02: タイトル正規化 ▼ ---  
    def _normalize_title(self, raw: dict):
        if not raw:                 
            return None             

        attributes = raw.get("attributes", {}) or {}            
        if "item_name" in attributes:                           
            try:                                
                return attributes["item_name"][0].get("value") 
            except Exception:                                   
                return None                                     
        return None                                             

    # --- ▼ SECTION 03: ブランド正規化 ▼ ---  
    def _normalize_brand(self, raw: dict):
        if not raw:                   
            return None               

        attributes = raw.get("attributes", {}) or {}        
        if "brand" in attributes:                           
            try:                                            
                return attributes["brand"][0].get("value") 
            except Exception:                               
                return None                                 
        return None                                         

    # --- ▼ SECTION 04: メーカー正規化（暫定） ▼ ---  
    def _normalize_manufacturer(self, raw: dict):
        """
        NOTE:
        旧 routes_listing では HOME の manufacturer は未取得。
        REGION 側は brand と同一方式で取得しているため、
        比較簡略化の目的で brand と完全同型の暫定実装とする。
        後続で要検証。
        """
        if not raw:
            return None

        attributes = raw.get("attributes", {}) or {}              
        if "manufacturer" in attributes:                          
            try:                                                   
                return attributes["manufacturer"][0].get("value")
            except Exception:                                      
                return None                                        
        return None    

    # --- ▼ SECTION 05: 寸法・重量正規化（HOME）  ▼ ---
    def _normalize_dimensions_weight(self, raw: dict) -> dict:
        if not raw:
            return {}

        raw_attr = raw.get("attributes", {}) or {}

        # === item_package_dimensions → fallback dimensions ===
        pkg_dims = None
        if "item_package_dimensions" in raw_attr:
            dims_list = raw_attr.get("item_package_dimensions")
            if isinstance(dims_list, list) and dims_list:
                pkg_dims = dims_list[0]

        if not pkg_dims:
            dims = raw.get("dimensions", {}) or {}
            pkg_dims = dims.get("package") or dims.get("item")

        # === 単位変換 ===
        def to_cm(value, unit):
            if value is None:
                return None
            u = (unit or "").lower()
            if "inch" in u:
                return float(value) * 2.54
            if "millimeter" in u or u == "mm":
                return float(value) / 10.0
            return float(value)

        def to_kg(value, unit):
            if value is None:
                return None
            u = "".join(str(unit or "").split()).lower()
            if "pound" in u or "lb" in u:
                return round(float(value) * 0.453592, 3)
            if "ounce" in u or u == "oz":
                return round(float(value) * 0.0283495, 3)
            if "kilogram" in u or u in {"kg", "kgs"}:
                return round(float(value), 3)
            if ("gram" in u and "kilogram" not in u) or u in {"g", "gr", "grm"}:
                return round(float(value) / 1000.0, 3)
            return round(float(value), 3)

        # === 寸法 ===
        length = width = height = None
        if isinstance(pkg_dims, dict):
            length = to_cm(pkg_dims.get("length", {}).get("value"),
                        pkg_dims.get("length", {}).get("unit"))
            width  = to_cm(pkg_dims.get("width", {}).get("value"),
                        pkg_dims.get("width", {}).get("unit"))
            height = to_cm(pkg_dims.get("height", {}).get("value"),
                        pkg_dims.get("height", {}).get("unit"))

        # === 重量 ===
        actual_weight = None

        if "item_package_weight" in raw_attr:
            try:
                w = raw_attr["item_package_weight"][0]
                actual_weight = to_kg(w.get("value"), w.get("unit"))
            except Exception:
                pass

        if actual_weight is None:
            w_raw = raw.get("weight")
            if isinstance(w_raw, dict):
                actual_weight = to_kg(w_raw.get("value"), w_raw.get("unit"))

        if actual_weight is None and isinstance(pkg_dims, dict):
            w_pkg = pkg_dims.get("weight")
            if isinstance(w_pkg, dict):
                actual_weight = to_kg(w_pkg.get("value"), w_pkg.get("unit"))

        # === 体積重量 / 請求重量 ===
        volumetric_weight = None
        billable_weight = None

        if length and width and height:
            volumetric_weight = (length * width * height) / 5000.0

        if actual_weight is not None and volumetric_weight is not None:
            billable_weight = max(actual_weight, volumetric_weight)

        return {
            "length_cm": length,
            "width_cm": width,
            "height_cm": height,
            "actual_weight_kg": actual_weight,
            "volumetric_weight_kg": volumetric_weight,
            "billable_weight_kg": billable_weight,
        }

    # --- ▼ SECTION 06: 画像正規化（HOME） ▼ ---
    def _normalize_home_image_url(self, raw: dict):
        """
        HOME Catalog RAW に含まれる images から
        正規化された image_url を抽出する。

        ・raw_json は加工しない
        ・選定・条件判断は行わない
        ・最終採用判断は rules 側に委譲
        """
        if not raw:
            return None  

        images = raw.get("images") or []  
        if not isinstance(images, list):
            return None  

        # images[0].images[0].link を最優先で使用
        try:
            first_block = images[0]
            image_list = first_block.get("images") or []
            if image_list and isinstance(image_list, list):
                return image_list[0].get("link")  
        except Exception:
            return None  

        return None  

    # --- ▼ SECTION 07: REGION brand / manufacturer 正規化 ▼ ---
    def _normalize_region_brand_manufacturer(self, raw: dict) -> dict:
        if not raw:
            return {
                "region_brand": "",
                "region_manufacturer": "",
            }

        raw_attr = raw.get("attributes", {}) or {}

        # brand
        brand = ""
        if "brand" in raw_attr:
            try:
                brand = raw_attr["brand"][0].get("value") or ""
            except Exception:
                brand = ""

        # manufacturer
        manufacturer = ""
        if "manufacturer" in raw_attr:
            try:
                manufacturer = raw_attr["manufacturer"][0].get("value") or ""
            except Exception:
                manufacturer = ""

        return {
            "region_brand": brand,
            "region_manufacturer": manufacturer,
        }


