import React, { useEffect, useRef, useState } from 'react';
import { toPng } from 'html-to-image';
import {
  CategoryDefinition,
  CategoryField,
  CategoryId,
  LayoutBox,
  ProductItem,
  TemplateSchema,
  WidgetBoxType,
} from '../types';
import { DynamicBannerCanvas } from './DynamicBannerCanvas';

const WIDGET_TYPES: Array<{ value: WidgetBoxType; label: string }> = [
  { value: 'header_banner', label: '🎨 ヘッダーバナー帯（色・タイトル・メーカー/型番）' },
  { value: 'kv_card', label: '📋 標準スペック枠（見出し帯＋値）' },
  { value: 'hero_metric', label: '🔢 特大数値枠（画面サイズ・容量・TOPS等）' },
  { value: 'boolean_badge', label: '⭕ 〇 / × 判定バッジ枠' },
  { value: 'spec_table', label: '📊 複数項目ミニテーブル枠' },
  { value: 'vod_grid', label: '🎬 ネット動画10社グリッド' },
  { value: 'energy_label_tv', label: '⭐ 省エネ性能（星評価・TV用）' },
  { value: 'energy_label_unified', label: '🌱 統一省エネラベル（緑枠・冷蔵庫/冷凍庫）' },
  { value: 'door_diagram_3d', label: '🚪 3Dドアレイアウト＋寸法図' },
  { value: 'door_swing_svg', label: '🔄 扉開閉イラスト図' },
  { value: 'dimension_diagram', label: '📐 本体サイズシルエット図' },
  { value: 'e_angle_select', label: '🟧 e angle Select オリジナル枠' },
  { value: 'jan_barcode', label: '🏷️ カラー＆JANバーコード枠' },
  { value: 'recycling_footer', label: '♻️ リサイクル料金フッター枠' },
  { value: 'point_callout', label: '💡 ■ Point 訴求見出し枠' },
];

export interface TemplateDesignerViewProps {
  categories: CategoryDefinition[];
  products: ProductItem[];
  showToastMsg: (text: string, type?: 'success' | 'info' | 'error') => void;
  onTemplatesUpdated?: () => void;
}

export const TemplateDesignerView: React.FC<TemplateDesignerViewProps> = ({
  categories,
  products,
  showToastMsg,
  onTemplatesUpdated,
}) => {
  const [templates, setTemplates] = useState<TemplateSchema[]>([]);
  const [activeCategory, setActiveCategory] = useState<CategoryId>('tv');
  const [currentTemplate, setCurrentTemplate] = useState<TemplateSchema | null>(null);
  const [selectedProduct, setSelectedProduct] = useState<ProductItem | null>(null);
  const [liveSpecs, setLiveSpecs] = useState<Record<string, any>>({});

  const [selectedBoxId, setSelectedBoxId] = useState<string | null>(null);
  const [selectedHeaderSlot, setSelectedHeaderSlot] = useState<string | null>(null);
  const [highlightedFieldKey, setHighlightedFieldKey] = useState<string | null>(null);
  const [rightTab, setRightTab] = useState<'mapping' | 'box_editor'>('mapping');

  const [zoom, setZoom] = useState<number>(1.0);
  const [showGrid, setShowGrid] = useState<boolean>(true);
  const [overlayOpacity, setOverlayOpacity] = useState<number>(0);
  const [analyzingImage, setAnalyzingImage] = useState<boolean>(false);
  const [visionSummary, setVisionSummary] = useState<string | null>(null);
  const [savingTemplate, setSavingTemplate] = useState<boolean>(false);
  const [exporting, setExporting] = useState<boolean>(false);

  // Publish modal state (target product / category default assignment)
  const [showPublishModal, setShowPublishModal] = useState<boolean>(false);
  const [publishAsCategoryDefault, setPublishAsCategoryDefault] = useState<boolean>(false);
  const [publishAssignedModels, setPublishAssignedModels] = useState<string[]>([]);

  // Add custom field state
  const [newFieldLabel, setNewFieldLabel] = useState<string>('');
  const [newFieldUnit, setNewFieldUnit] = useState<string>('');
  const [newFieldValue, setNewFieldValue] = useState<string>('');

  const dynamicCanvasRef = useRef<HTMLDivElement | null>(null);
  const imageInputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    loadTemplates('tv');
  }, []);

  const loadTemplates = async (cat: CategoryId, selectTemplateId?: string) => {
    try {
      const res = await fetch('/api/templates');
      const data = await res.json();
      const allItems: TemplateSchema[] = data.items || [];
      setTemplates(allItems);

      const targetTpl =
        (selectTemplateId && allItems.find((t) => t.template_id === selectTemplateId)) ||
        allItems.find((t) => t.category === cat) ||
        allItems[0];

      if (targetTpl) {
        applyTemplate(targetTpl, cat);
      }
    } catch (err: any) {
      showToastMsg(`テンプレート読込エラー: ${err.message}`, 'error');
    }
  };

  const applyTemplate = (tpl: TemplateSchema, catOverride?: CategoryId) => {
    const cat = (catOverride || tpl.category || 'tv') as CategoryId;
    setActiveCategory(cat);
    setCurrentTemplate(JSON.parse(JSON.stringify(tpl)));
    setSelectedBoxId(tpl.boxes[0]?.id || null);
    setSelectedHeaderSlot(null);
    setPublishAsCategoryDefault(Boolean(tpl.is_category_default));
    setPublishAssignedModels(tpl.assigned_models || []);

    const catProds = products.filter((p) => p.category === cat);
    const prod = catProds[0] || products[0] || null;
    if (prod) {
      setSelectedProduct(prod);
      const mergedSpecs = { ...(prod.specs || {}) };
      for (const cf of tpl.custom_fields || []) {
        if (mergedSpecs[cf.key] === undefined && cf.default !== undefined) {
          mergedSpecs[cf.key] = cf.default;
        }
      }
      setLiveSpecs(mergedSpecs);
    }
  };

  /**
   * Starts a 100% blank template ("白紙から新規作成") with ZERO pre-filled header or boxes
   * so the user can add a header object or spec boxes freely from scratch!
   */
  const handleStartBlankCanvas = () => {
    const catDef = categories.find((c) => c.id === activeCategory);
    const isLandscape = (catDef?.orientation || 'landscape') === 'landscape';
    const blankTpl: TemplateSchema = {
      template_id: `blank_${activeCategory}_${Date.now().toString().slice(-5)}`,
      name: `【新規作成】${catDef?.name || activeCategory} カスタムテンプレート`,
      category: activeCategory,
      orientation: isLandscape ? 'landscape' : 'portrait',
      is_preset: false,
      status: 'draft',
      is_category_default: false,
      assigned_models: selectedProduct ? [selectedProduct.search_model_no] : [],
      canvas_width: isLandscape ? 820 : 552,
      canvas_height: isLandscape ? 568 : 760,
      canvas_bg_color: isLandscape ? '#EAEAEA' : '#FFFFFF',
      outer_padding: 12,
      grid_snap_px: 4,
      header: {
        visible: false,
        height: 84,
        default_bg_color: '#1B9E3E',
        text_color: '#FFFFFF',
        main_title_mode: 'static',
        main_title_field_key: '',
        main_title_static: '',
        top_right_1_field_key: '',
        top_right_2_field_key: '',
        bottom_right_field_key: '',
        sub_left_field_key: '',
      },
      boxes: [],
      custom_fields: [],
    };
    setCurrentTemplate(blankTpl);
    setSelectedBoxId(null);
    setSelectedHeaderSlot(null);
    setVisionSummary(null);
    setOverlayOpacity(0);
    setPublishAsCategoryDefault(false);
    setPublishAssignedModels(selectedProduct ? [selectedProduct.search_model_no] : []);
    showToastMsg(
      '✨ 完全に空の白紙キャンバスを作成しました！「＋ ヘッダー枠」「＋ 標準枠」「＋ 特大数値枠」から自由にオブジェクトを追加できます。',
      'info'
    );
  };

  const handleCategorySwitch = (cat: CategoryId) => {
    setActiveCategory(cat);
    const tpl = templates.find((t) => t.category === cat);
    if (tpl) {
      applyTemplate(tpl, cat);
    }
  };

  const handleProductSwitch = (prodIdent: string) => {
    const p = products.find(
      (item) => item.search_model_no === prodIdent || item.jan_code === prodIdent
    );
    if (!p) return;
    setSelectedProduct(p);
    setLiveSpecs((prev) => ({ ...prev, ...(p.specs || {}) }));
  };

  const currentCatDef = categories.find((c) => c.id === activeCategory);
  const allFields: CategoryField[] = React.useMemo(() => {
    const base = currentCatDef?.fields || [];
    const custom = currentTemplate?.custom_fields || [];
    const existingKeys = new Set(base.map((f) => f.key));
    return [...base, ...custom.filter((cf) => !existingKeys.has(cf.key))];
  }, [currentCatDef, currentTemplate?.custom_fields]);

  const selectedBox = React.useMemo(() => {
    if (!currentTemplate || !selectedBoxId) return null;
    return currentTemplate.boxes.find((b) => b.id === selectedBoxId) || null;
  }, [currentTemplate, selectedBoxId]);

  const updateBox = (boxId: string, patch: Partial<LayoutBox>) => {
    setCurrentTemplate((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        boxes: prev.boxes.map((b) => (b.id === boxId ? { ...b, ...patch } : b)),
      };
    });
  };

  const bindFieldToBox = (boxId: string, fieldKey: string, fieldLabel?: string) => {
    const fDef = allFields.find((f) => f.key === fieldKey);
    const labelToUse = fieldLabel || fDef?.label || fieldKey;
    setCurrentTemplate((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        boxes: prev.boxes.map((b) =>
          b.id === boxId
            ? {
                ...b,
                title: labelToUse,
                binding: {
                  ...b.binding,
                  field_key: fieldKey,
                  label_override: labelToUse,
                  unit_override: fDef?.unit ?? null,
                },
              }
            : b
        ),
      };
    });
    setSelectedBoxId(boxId);
    setHighlightedFieldKey(fieldKey);
    showToastMsg(`枠「${labelToUse}」に項目「${fieldKey}」を割り当てました`);
  };

  const bindFieldToHeaderSlot = (slotName: string, fieldKey: string) => {
    setCurrentTemplate((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        header: {
          ...prev.header,
          ...(slotName === 'main_title_field_key' ? { main_title_mode: 'field' as const } : {}),
          [slotName]: fieldKey,
        },
      };
    });
    setSelectedHeaderSlot(slotName);
    setHighlightedFieldKey(fieldKey);
    showToastMsg(`ヘッダー領域に項目「${fieldKey}」を割り当てました`);
  };

  /**
   * Changes where a right-hand field is output on the main banner!
   * Users can assign any field to any existing box, any header slot, or create a new box for it.
   */
  const handleAssignFieldDestination = (field: CategoryField, targetValue: string) => {
    if (!currentTemplate) return;

    if (targetValue === '__new_box__') {
      const newId = `box_${field.key}_${Date.now().toString().slice(-4)}`;
      const newBox: LayoutBox = {
        id: newId,
        box_type: 'kv_card',
        title: field.label,
        show_title_bar: true,
        title_bg_color: '#666666',
        title_text_color: '#FFFFFF',
        bg_color: '#FFFFFF',
        border_color: '#999999',
        border_width: 1.5,
        border_radius: 0,
        x: 24,
        y: (currentTemplate.header.height || 84) + 16,
        w: 168,
        h: 84,
        value_font_size: 'auto',
        value_color: '#111111',
        text_align: 'center',
        binding: {
          field_key: field.key,
          label_override: field.label,
          unit_override: field.unit || null,
          prefix_text: null,
          sub_field_keys: [],
          empty_fallback: '-',
        },
      };
      setCurrentTemplate((prev) => (prev ? { ...prev, boxes: [...prev.boxes, newBox] } : prev));
      setSelectedBoxId(newId);
      setHighlightedFieldKey(field.key);
      showToastMsg(`「${field.label}」用の新しい枠をメイン画面に追加しました`);
      return;
    }

    if (targetValue.startsWith('hbox:')) {
      const [, boxId, slotIdxStr] = targetValue.split(':');
      const slotIdx = parseInt(slotIdxStr, 10);
      setCurrentTemplate((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          boxes: prev.boxes.map((b) => {
            if (b.id !== boxId) return b;
            const nextSub = [...(b.binding.sub_field_keys || ['', '', ''])];
            while (nextSub.length < 3) nextSub.push('');
            nextSub[slotIdx] = field.key;
            return {
              ...b,
              binding: {
                ...b.binding,
                sub_field_keys: nextSub,
              },
            };
          }),
        };
      });
      setSelectedBoxId(boxId);
      setHighlightedFieldKey(field.key);
      showToastMsg(`ヘッダーバナー枠に項目「${field.label}」を割り当てました`);
      return;
    }

    if (targetValue.startsWith('header:')) {
      const slotKey = targetValue.replace('header:', '');
      bindFieldToHeaderSlot(slotKey, field.key);
      return;
    }

    if (targetValue.startsWith('box:')) {
      const boxId = targetValue.replace('box:', '');
      bindFieldToBox(boxId, field.key, field.label);
    }
  };

  const handleAddBox = (boxType: WidgetBoxType = 'kv_card') => {
    if (!currentTemplate) return;
    if (boxType === 'header_banner') {
      const defaultBg =
        activeCategory === 'tv'
          ? '#1B9E3E'
          : activeCategory === 'pc'
          ? '#1F4E78'
          : activeCategory === 'freezer'
          ? '#1C549D'
          : activeCategory === 'refrigerator'
          ? '#009250'
          : '#007A70';
      const newHeaderId = `box_header_${Date.now().toString().slice(-4)}`;
      const newHeaderBox: LayoutBox = {
        id: newHeaderId,
        box_type: 'header_banner',
        title: `${currentCatDef?.name || '新規'} 機能表`,
        show_title_bar: false,
        title_bg_color: defaultBg,
        title_text_color: '#FFFFFF',
        bg_color: defaultBg,
        border_color: defaultBg,
        border_width: 0,
        border_radius: 0,
        x: 0,
        y: 0,
        w: currentTemplate.canvas_width,
        h: 84,
        value_font_size: 'auto',
        value_color: '#FFFFFF',
        text_align: 'left',
        binding: {
          field_key: activeCategory === 'tv' ? 'type' : activeCategory === 'pc' ? 'brand_logo' : 'maker',
          label_override: `${currentCatDef?.name || '新規'} 機能表`,
          unit_override: null,
          prefix_text: null,
          sub_field_keys: ['maker', activeCategory === 'tv' ? 'brand' : '', 'model_no'],
          empty_fallback: '',
        },
      };
      setCurrentTemplate((prev) =>
        prev ? { ...prev, boxes: [newHeaderBox, ...prev.boxes] } : prev
      );
      setSelectedBoxId(newHeaderId);
      setRightTab('box_editor');
      showToastMsg('🎨 ヘッダーバナー枠を追加しました！背景色・サイズ・位置・出力項目を自由に変更できます。');
      return;
    }

    const firstField = allFields[0] || { key: 'maker', label: '新規項目', unit: null };
    const newId = `box_custom_${Date.now().toString().slice(-4)}`;
    const hasHeaderBox = currentTemplate.boxes.some((b) => b.box_type === 'header_banner');
    const newBox: LayoutBox = {
      id: newId,
      box_type: boxType,
      title: firstField.label,
      show_title_bar: !['energy_label_unified', 'energy_label_tv', 'e_angle_select', 'recycling_footer'].includes(
        boxType
      ),
      title_bg_color: '#666666',
      title_text_color: '#FFFFFF',
      bg_color: '#FFFFFF',
      border_color: '#999999',
      border_width: 1.5,
      border_radius: 0,
      x: 24,
      y: hasHeaderBox ? 96 : 24,
      w: boxType === 'hero_metric' ? 220 : 164,
      h: boxType === 'hero_metric' ? 140 : 88,
      value_font_size: 'auto',
      value_color: '#111111',
      text_align: 'center',
      binding: {
        field_key: firstField.key,
        label_override: firstField.label,
        unit_override: firstField.unit || null,
        prefix_text: null,
        sub_field_keys: [],
        empty_fallback: '-',
      },
    };
    setCurrentTemplate((prev) => (prev ? { ...prev, boxes: [...prev.boxes, newBox] } : prev));
    setSelectedBoxId(newId);
    setRightTab('box_editor');
  };

  const handleDuplicateSelectedBox = () => {
    if (!currentTemplate || !selectedBox) return;
    const dupId = `${selectedBox.id}_copy_${Date.now().toString().slice(-3)}`;
    const dupBox: LayoutBox = {
      ...JSON.parse(JSON.stringify(selectedBox)),
      id: dupId,
      x: Math.min(currentTemplate.canvas_width - selectedBox.w - 8, selectedBox.x + 16),
      y: Math.min(currentTemplate.canvas_height - selectedBox.h - 8, selectedBox.y + 16),
    };
    setCurrentTemplate((prev) => (prev ? { ...prev, boxes: [...prev.boxes, dupBox] } : prev));
    setSelectedBoxId(dupId);
  };

  const handleDeleteSelectedBox = () => {
    if (!currentTemplate || !selectedBoxId) return;
    setCurrentTemplate((prev) => {
      if (!prev) return prev;
      const remaining = prev.boxes.filter((b) => b.id !== selectedBoxId);
      setSelectedBoxId(remaining[0]?.id || null);
      return { ...prev, boxes: remaining };
    });
  };

  const handleAddCustomField = () => {
    if (!newFieldLabel.trim() || !currentTemplate) return;
    const key = `custom_${Date.now().toString().slice(-5)}`;
    const cf: CategoryField = {
      key,
      label: newFieldLabel.trim(),
      group: 'カスタム追加項目',
      type: 'text',
      unit: newFieldUnit.trim() || null,
      choices: null,
      default: newFieldValue,
    };
    setCurrentTemplate((prev) =>
      prev
        ? {
            ...prev,
            custom_fields: [...(prev.custom_fields || []), cf],
          }
        : prev
    );
    setLiveSpecs((prev) => ({ ...prev, [key]: newFieldValue || 'サンプル値' }));
    setNewFieldLabel('');
    setNewFieldUnit('');
    setNewFieldValue('');
    showToastMsg(`カスタム項目「${cf.label}」を追加しました。任意の枠に割り当て可能です！`);
  };

  const handleImageUploadForVision = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setAnalyzingImage(true);
    setVisionSummary(null);
    showToastMsg('📷 Gemini 2.5 Flash Vision で枠（レイアウト）画像を解析しています...', 'info');
    try {
      const formData = new FormData();
      formData.append('file', file);
      const res = await fetch(
        `/api/templates/analyze-image?category=${encodeURIComponent(activeCategory)}`,
        {
          method: 'POST',
          body: formData,
        }
      );
      if (!res.ok) throw new Error('画像レイアウト解析に失敗しました');
      const data = await res.json();
      const newTpl: TemplateSchema = data.template;
      setCurrentTemplate(newTpl);
      if (data.extracted_specs && Object.keys(data.extracted_specs).length > 0) {
        setLiveSpecs((prev) => ({ ...prev, ...data.extracted_specs }));
      }
      setSelectedBoxId(newTpl.boxes[0]?.id || null);
      setVisionSummary(data.summary || '画像からレイアウト枠と項目マッピングを自動生成しました。');
      setOverlayOpacity(0);
      showToastMsg('✨ 添付画像のレイアウト枠＆項目配置をキャンバスに自動反映しました！');
    } catch (err: any) {
      showToastMsg(err.message, 'error');
    } finally {
      setAnalyzingImage(false);
      if (imageInputRef.current) imageInputRef.current.value = '';
    }
  };

  const captureCleanBannerDataUrl = async (): Promise<string | null> => {
    if (!dynamicCanvasRef.current) return null;
    const prevBox = selectedBoxId;
    const prevHeader = selectedHeaderSlot;
    const prevHigh = highlightedFieldKey;
    const prevOverlay = overlayOpacity;
    try {
      setSelectedBoxId(null);
      setSelectedHeaderSlot(null);
      setHighlightedFieldKey(null);
      setOverlayOpacity(0);
      await new Promise((r) => setTimeout(r, 80));
      if (document.fonts && document.fonts.ready) {
        await document.fonts.ready;
      }
      const dataUrl = await toPng(dynamicCanvasRef.current, {
        pixelRatio: 3.0,
        backgroundColor: '#FFFFFF',
        cacheBust: true,
        filter: (node: any) => {
          return !(node?.dataset && node.dataset.exportIgnore === 'true');
        },
      });
      return dataUrl;
    } catch (e) {
      console.warn('Clean capture error:', e);
      return null;
    } finally {
      setSelectedBoxId(prevBox);
      setSelectedHeaderSlot(prevHeader);
      setHighlightedFieldKey(prevHigh);
      setOverlayOpacity(prevOverlay);
    }
  };

  const handleSaveTemplate = async (
    targetStatus: 'draft' | 'published' = 'draft',
    asCategoryDefault: boolean = false,
    assignedModels: string[] = []
  ) => {
    if (!currentTemplate) return;
    if (!currentTemplate.name.trim()) {
      showToastMsg('テンプレート名を入力してください', 'error');
      return;
    }
    setSavingTemplate(true);
    try {
      const dataUrl = await captureCleanBannerDataUrl();
      const updatedTpl: TemplateSchema = {
        ...currentTemplate,
        status: targetStatus,
        is_category_default: asCategoryDefault,
        assigned_models: assignedModels,
      };
      const res = await fetch('/api/templates', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          template_id: currentTemplate.template_id,
          name: currentTemplate.name,
          category: activeCategory,
          orientation: currentTemplate.orientation,
          status: targetStatus,
          is_category_default: asCategoryDefault,
          assigned_models: assignedModels,
          schema_json: updatedTpl,
          image_data_url: dataUrl,
        }),
      });
      if (!res.ok) throw new Error('テンプレート保存に失敗しました');
      const saved: TemplateSchema = await res.json();
      await loadTemplates(activeCategory, saved.template_id);
      if (onTemplatesUpdated) {
        onTemplatesUpdated();
      }
      setShowPublishModal(false);
      if (targetStatus === 'published') {
        showToastMsg(
          `🚀 テンプレート「${saved.name}」を公開しました！「標準 機能表スタジオ」でも選択・自動適用されます。`
        );
      } else {
        showToastMsg(`📝 テンプレート「${saved.name}」を一時保存（下書き）しました。`);
      }
    } catch (err: any) {
      showToastMsg(err.message, 'error');
    } finally {
      setSavingTemplate(false);
    }
  };

  const handleExportDynamic = async (format: 'jpeg' | 'pdf') => {
    if (!currentTemplate) return;
    setExporting(true);
    try {
      const dataUrl = await captureCleanBannerDataUrl();
      const modelNo = liveSpecs.model_no || selectedProduct?.search_model_no || activeCategory;
      const ext = format === 'jpeg' ? 'jpg' : 'pdf';
      const filename = `Cymbal_カスタム機能表_${modelNo}.${ext}`;
      const res = await fetch(`/api/export/${format}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          category: activeCategory,
          specs: liveSpecs,
          image_data_url: dataUrl,
          filename,
        }),
      });
      if (!res.ok) throw new Error(`${format.toUpperCase()}出力に失敗しました`);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      showToastMsg(`${filename} をダウンロードしました`);
    } catch (err: any) {
      showToastMsg(err.message, 'error');
    } finally {
      setExporting(false);
    }
  };

  const findWhereFieldIsBound = (fieldKey: string): string => {
    if (!currentTemplate) return '';
    // Check header_banner sub_field_keys first
    for (const b of currentTemplate.boxes) {
      if (b.box_type === 'header_banner') {
        const subs = b.binding.sub_field_keys || [];
        if (subs[0] === fieldKey) return `hbox:${b.id}:0`;
        if (subs[1] === fieldKey) return `hbox:${b.id}:1`;
        if (subs[2] === fieldKey) return `hbox:${b.id}:2`;
      }
    }
    const matchedBox = currentTemplate.boxes.find((b) => b.binding.field_key === fieldKey);
    if (matchedBox) return `box:${matchedBox.id}`;

    const h = currentTemplate.header;
    if (h.visible) {
      if (h.top_right_1_field_key === fieldKey) return 'header:top_right_1_field_key';
      if (h.top_right_2_field_key === fieldKey) return 'header:top_right_2_field_key';
      if (h.bottom_right_field_key === fieldKey) return 'header:bottom_right_field_key';
      if (h.main_title_mode === 'field' && h.main_title_field_key === fieldKey)
        return 'header:main_title_field_key';
      if (h.sub_left_field_key === fieldKey) return 'header:sub_left_field_key';
    }
    return '';
  };

  if (!currentTemplate) {
    return <div style={{ padding: 32 }}>テンプレートを読み込み中...</div>;
  }

  const categoryProducts = products.filter((p) => p.category === activeCategory);

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0 }}>
      {/* Sub-navigation bar for Designer Lab */}
      <div
        style={{
          background: '#1E1B4B',
          color: '#FFFFFF',
          padding: '8px 20px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 12,
          flexWrap: 'wrap',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <span
            style={{
              background: '#7C3AED',
              color: '#FFFFFF',
              padding: '3px 10px',
              borderRadius: 14,
              fontSize: 11.5,
              fontWeight: 900,
            }}
          >
            🧩 カテゴリ別テンプレート・項目配置編集
          </span>

          {categories.map((cat) => {
            const active = activeCategory === cat.id;
            return (
              <button
                key={cat.id}
                onClick={() => handleCategorySwitch(cat.id)}
                style={{
                  background: active ? '#F59E0B' : 'rgba(255,255,255,0.12)',
                  color: active ? '#111827' : '#FFFFFF',
                  border: 'none',
                  borderRadius: 16,
                  padding: '5px 12px',
                  fontSize: 12,
                  fontWeight: 800,
                  cursor: 'pointer',
                }}
              >
                {cat.name}
              </button>
            );
          })}
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{ fontSize: 12, fontWeight: 700 }}>テスト表示商品:</span>
          <select
            value={selectedProduct?.search_model_no || ''}
            onChange={(e) => handleProductSwitch(e.target.value)}
            style={{
              padding: '5px 10px',
              borderRadius: 6,
              border: '1px solid #6366F1',
              fontSize: 12,
              fontWeight: 700,
              background: '#FFFFFF',
              color: '#0F172A',
            }}
          >
            {categoryProducts.map((p) => (
              <option key={p.search_model_no} value={p.search_model_no}>
                {p.maker_name || p.specs?.maker} - {p.search_model_no} ({p.product_name})
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Main 3-Pane Designer Workspace */}
      <div
        style={{
          flex: 1,
          display: 'grid',
          gridTemplateColumns: '330px 1fr 440px',
          minHeight: 0,
        }}
      >
        {/* LEFT PANE: AI Image Upload + Template Selector + Frame/Box Tree */}
        <aside
          style={{
            background: '#FFFFFF',
            borderRight: '1px solid #CBD5E1',
            display: 'flex',
            flexDirection: 'column',
            height: 'calc(100vh - 106px)',
            overflowY: 'auto',
            padding: 12,
            gap: 12,
          }}
        >
          {/* Section 1: AI Vision Layout Generator from Image */}
          <div
            style={{
              background: 'linear-gradient(135deg, #EEF2FF 0%, #F5F3FF 100%)',
              border: '2px dashed #6366F1',
              borderRadius: 10,
              padding: 12,
            }}
          >
            <div style={{ fontSize: 13, fontWeight: 900, color: '#312E81', marginBottom: 4 }}>
              📷 枠（レイアウト）画像から自動生成
            </div>
            <div style={{ fontSize: 11, color: '#4338CA', lineHeight: 1.4, marginBottom: 8 }}>
              機能表やPOPのレイアウト画像（JPEG/PNG）を添付すると、Gemini 2.5 Flash Vision が枠の位置・サイズ・出力項目を自動解析して反映します。
            </div>
            <input
              ref={imageInputRef}
              type="file"
              accept="image/jpeg,image/png,image/webp"
              style={{ display: 'none' }}
              onChange={handleImageUploadForVision}
            />
            <button
              onClick={() => imageInputRef.current?.click()}
              disabled={analyzingImage}
              style={{
                width: '100%',
                background: '#4F46E5',
                color: '#FFFFFF',
                border: 'none',
                borderRadius: 7,
                padding: '9px 12px',
                fontSize: 12.5,
                fontWeight: 900,
                cursor: 'pointer',
                boxShadow: '0 2px 6px rgba(79, 70, 229, 0.3)',
              }}
            >
              {analyzingImage
                ? '⏳ AIが画像の枠・項目を解析中...'
                : '📤 レイアウト画像を添付して自動反映'}
            </button>

            {visionSummary && (
              <div
                style={{
                  marginTop: 8,
                  background: '#FFFFFF',
                  border: '1px solid #C7D2FE',
                  borderRadius: 6,
                  padding: 8,
                  fontSize: 11,
                  color: '#1E1B4B',
                }}
              >
                <strong>✨ AI解析結果:</strong> {visionSummary}
              </div>
            )}

            {currentTemplate.source_image_data_url && (
              <div style={{ marginTop: 8 }}>
                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    fontSize: 11,
                    fontWeight: 700,
                    color: '#312E81',
                  }}
                >
                  <span>添付元画像の透過重ね合わせ:</span>
                  <span>{Math.round(overlayOpacity * 100)}%</span>
                </div>
                <input
                  type="range"
                  min={0}
                  max={0.8}
                  step={0.05}
                  value={overlayOpacity}
                  onChange={(e) => setOverlayOpacity(parseFloat(e.target.value))}
                  style={{ width: '100%' }}
                />
              </div>
            )}
          </div>

          {/* Section 2: Template Name, Blank Creation & Canvas Orientation */}
          <div
            style={{
              background: '#F8FAFC',
              border: '1px solid #E2E8F0',
              borderRadius: 8,
              padding: 10,
            }}
          >
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                marginBottom: 8,
              }}
            >
              <span style={{ fontSize: 12, fontWeight: 900, color: '#0F172A' }}>
                🗂️ テンプレート選択・新規作成
              </span>
              <button
                onClick={handleStartBlankCanvas}
                style={{
                  background: '#0F172A',
                  color: '#FFFFFF',
                  border: 'none',
                  borderRadius: 5,
                  padding: '4px 9px',
                  fontSize: 11,
                  fontWeight: 800,
                  cursor: 'pointer',
                  whiteSpace: 'nowrap',
                }}
              >
                📄 白紙から新規作成
              </button>
            </div>

            <select
              value={currentTemplate.template_id}
              onChange={(e) => {
                const found = templates.find((t) => t.template_id === e.target.value);
                if (found) applyTemplate(found);
              }}
              style={{
                width: '100%',
                padding: '6px 8px',
                borderRadius: 6,
                border: '1px solid #CBD5E1',
                fontSize: 12,
                fontWeight: 700,
                marginBottom: 8,
              }}
            >
              {currentTemplate.template_id.startsWith('blank_') && (
                <option value={currentTemplate.template_id}>
                  🆕 {currentTemplate.name} (未保存)
                </option>
              )}
              {templates
                .filter((t) => t.category === activeCategory)
                .map((t) => (
                  <option key={t.template_id} value={t.template_id}>
                    {t.is_preset
                      ? '⭐ [標準] '
                      : t.status === 'published'
                      ? '🚀 [公開中] '
                      : '📝 [一時保存] '}
                    {t.name}
                  </option>
                ))}
            </select>

            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                marginBottom: 2,
              }}
            >
              <label style={{ fontSize: 11, fontWeight: 700, color: '#475569' }}>
                テンプレート名（保存名）:
              </label>
              <span
                style={{
                  fontSize: 10,
                  fontWeight: 800,
                  padding: '1px 6px',
                  borderRadius: 10,
                  background:
                    currentTemplate.status === 'published'
                      ? '#DCFCE7'
                      : currentTemplate.is_preset
                      ? '#E0E7FF'
                      : '#FEF3C7',
                  color:
                    currentTemplate.status === 'published'
                      ? '#166534'
                      : currentTemplate.is_preset
                      ? '#3730A3'
                      : '#92400E',
                }}
              >
                {currentTemplate.status === 'published'
                  ? '🚀 公開済（標準スタジオ利用可）'
                  : currentTemplate.is_preset
                  ? '⭐ 標準プリセット'
                  : '📝 一時保存（下書き）'}
              </span>
            </div>
            <input
              type="text"
              value={currentTemplate.name}
              placeholder="新しいテンプレート名を入力..."
              onChange={(e) =>
                setCurrentTemplate((prev) => (prev ? { ...prev, name: e.target.value } : prev))
              }
              style={{
                width: '100%',
                padding: '6px 8px',
                borderRadius: 5,
                border: '1px solid #CBD5E1',
                fontSize: 12,
                fontWeight: 700,
                boxSizing: 'border-box',
                marginTop: 2,
                marginBottom: 8,
              }}
            />

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 6 }}>
              <div>
                <label style={{ fontSize: 10.5, fontWeight: 700 }}>幅(W px)</label>
                <input
                  type="number"
                  value={currentTemplate.canvas_width}
                  onChange={(e) =>
                    setCurrentTemplate((prev) =>
                      prev ? { ...prev, canvas_width: Number(e.target.value) || 820 } : prev
                    )
                  }
                  style={{ width: '100%', padding: 4, fontSize: 12, boxSizing: 'border-box' }}
                />
              </div>
              <div>
                <label style={{ fontSize: 10.5, fontWeight: 700 }}>高さ(H px)</label>
                <input
                  type="number"
                  value={currentTemplate.canvas_height}
                  onChange={(e) =>
                    setCurrentTemplate((prev) =>
                      prev ? { ...prev, canvas_height: Number(e.target.value) || 568 } : prev
                    )
                  }
                  style={{ width: '100%', padding: 4, fontSize: 12, boxSizing: 'border-box' }}
                />
              </div>
              <div>
                <label style={{ fontSize: 10.5, fontWeight: 700 }}>背景色</label>
                <input
                  type="color"
                  value={currentTemplate.canvas_bg_color || '#EAEAEA'}
                  onChange={(e) =>
                    setCurrentTemplate((prev) =>
                      prev ? { ...prev, canvas_bg_color: e.target.value } : prev
                    )
                  }
                  style={{ width: '100%', height: 28, cursor: 'pointer' }}
                />
              </div>
            </div>
          </div>

          {/* Section 3: Add / Manage Layout Boxes */}
          <div
            style={{
              background: '#F8FAFC',
              border: '1px solid #E2E8F0',
              borderRadius: 8,
              padding: 10,
              flex: 1,
              display: 'flex',
              flexDirection: 'column',
              minHeight: 220,
            }}
          >
            <div
              style={{
                display: 'flex',
                flexDirection: 'column',
                gap: 6,
                marginBottom: 8,
              }}
            >
              <span style={{ fontSize: 12, fontWeight: 900, color: '#0F172A' }}>
                🧱 オブジェクト・枠一覧 ({currentTemplate.boxes.length})
              </span>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 4 }}>
                <button
                  onClick={() => handleAddBox('header_banner')}
                  style={{
                    background: '#7C3AED',
                    color: '#FFFFFF',
                    border: 'none',
                    borderRadius: 5,
                    padding: '5px 6px',
                    fontSize: 10.5,
                    fontWeight: 800,
                    cursor: 'pointer',
                    whiteSpace: 'nowrap',
                  }}
                >
                  ＋ ヘッダー枠
                </button>
                <button
                  onClick={() => handleAddBox('kv_card')}
                  style={{
                    background: '#0284C7',
                    color: '#FFFFFF',
                    border: 'none',
                    borderRadius: 5,
                    padding: '5px 6px',
                    fontSize: 10.5,
                    fontWeight: 800,
                    cursor: 'pointer',
                    whiteSpace: 'nowrap',
                  }}
                >
                  ＋ 標準枠追加
                </button>
                <button
                  onClick={() => handleAddBox('hero_metric')}
                  style={{
                    background: '#059669',
                    color: '#FFFFFF',
                    border: 'none',
                    borderRadius: 5,
                    padding: '5px 6px',
                    fontSize: 10.5,
                    fontWeight: 800,
                    cursor: 'pointer',
                    whiteSpace: 'nowrap',
                  }}
                >
                  ＋ 特大数値枠
                </button>
              </div>
            </div>

            <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 4 }}>
              {currentTemplate.boxes.map((b) => {
                const isSel = selectedBoxId === b.id;
                return (
                  <div
                    key={b.id}
                    onClick={() => {
                      setSelectedBoxId(b.id);
                      setHighlightedFieldKey(b.binding.field_key);
                      setRightTab('box_editor');
                    }}
                    style={{
                      padding: '6px 8px',
                      borderRadius: 6,
                      background: isSel ? '#EFF6FF' : '#FFFFFF',
                      border: isSel ? '2px solid #2563EB' : '1px solid #CBD5E1',
                      cursor: 'pointer',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      fontSize: 11.5,
                    }}
                  >
                    <div style={{ minWidth: 0 }}>
                      <div style={{ fontWeight: 800, color: '#0F172A' }}>{b.title}</div>
                      <div style={{ fontSize: 10, color: '#64748B' }}>
                        出力項目: <code>{b.binding.field_key}</code> ({b.x},{b.y} / {b.w}×{b.h})
                      </div>
                    </div>
                    <span
                      style={{
                        background: '#E2E8F0',
                        color: '#334155',
                        fontSize: 9.5,
                        fontWeight: 700,
                        padding: '2px 5px',
                        borderRadius: 4,
                        flexShrink: 0,
                      }}
                    >
                      {b.box_type}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        </aside>

        {/* CENTER PANE: Interactive Banner Canvas */}
        <main
          style={{
            display: 'flex',
            flexDirection: 'column',
            height: 'calc(100vh - 106px)',
            overflow: 'hidden',
          }}
        >
          {/* Toolbar */}
          <div
            style={{
              background: '#FFFFFF',
              borderBottom: '1px solid #CBD5E1',
              padding: '9px 16px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              flexWrap: 'wrap',
              gap: 8,
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <span style={{ fontSize: 12, fontWeight: 800, color: '#475569' }}>倍率:</span>
              {[0.75, 1.0, 1.15].map((z) => (
                <button
                  key={z}
                  onClick={() => setZoom(z)}
                  style={{
                    background: zoom === z ? '#0F172A' : '#F1F5F9',
                    color: zoom === z ? '#FFFFFF' : '#334155',
                    border: '1px solid #CBD5E1',
                    borderRadius: 5,
                    padding: '4px 8px',
                    fontSize: 11.5,
                    fontWeight: 800,
                    cursor: 'pointer',
                  }}
                >
                  {Math.round(z * 100)}%
                </button>
              ))}

              <button
                onClick={() => setShowGrid((prev) => !prev)}
                style={{
                  marginLeft: 4,
                  background: showGrid ? '#DBEAFE' : '#F8FAFC',
                  color: showGrid ? '#1D4ED8' : '#475569',
                  border: '1px solid #93C5FD',
                  borderRadius: 5,
                  padding: '4px 10px',
                  fontSize: 11.5,
                  fontWeight: 800,
                  cursor: 'pointer',
                }}
              >
                📏 スナップグリッド {showGrid ? 'ON' : 'OFF'}
              </button>

              {selectedBox && (
                <>
                  <button
                    onClick={handleDuplicateSelectedBox}
                    style={{
                      background: '#F1F5F9',
                      color: '#0F172A',
                      border: '1px solid #CBD5E1',
                      borderRadius: 5,
                      padding: '4px 9px',
                      fontSize: 11.5,
                      fontWeight: 800,
                      cursor: 'pointer',
                    }}
                  >
                    📋 選択枠を複製
                  </button>
                  <button
                    onClick={handleDeleteSelectedBox}
                    style={{
                      background: '#FEE2E2',
                      color: '#B91C1C',
                      border: '1px solid #FCA5A5',
                      borderRadius: 5,
                      padding: '4px 9px',
                      fontSize: 11.5,
                      fontWeight: 800,
                      cursor: 'pointer',
                    }}
                  >
                    🗑️ 選択枠を削除
                  </button>
                </>
              )}
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <button
                onClick={() => handleExportDynamic('jpeg')}
                disabled={exporting}
                style={{
                  background: '#0284C7',
                  color: '#FFFFFF',
                  border: 'none',
                  borderRadius: 6,
                  padding: '6px 11px',
                  fontSize: 11.5,
                  fontWeight: 800,
                  cursor: 'pointer',
                  whiteSpace: 'nowrap',
                }}
              >
                🖼️ JPEG 出力
              </button>
              <button
                onClick={() => handleExportDynamic('pdf')}
                disabled={exporting}
                style={{
                  background: '#059669',
                  color: '#FFFFFF',
                  border: 'none',
                  borderRadius: 6,
                  padding: '6px 11px',
                  fontSize: 11.5,
                  fontWeight: 800,
                  cursor: 'pointer',
                  whiteSpace: 'nowrap',
                }}
              >
                📄 PDF 出力
              </button>
              <button
                onClick={() =>
                  handleSaveTemplate(
                    'draft',
                    publishAsCategoryDefault,
                    publishAssignedModels
                  )
                }
                disabled={savingTemplate}
                style={{
                  background: '#475569',
                  color: '#FFFFFF',
                  border: 'none',
                  borderRadius: 6,
                  padding: '6px 12px',
                  fontSize: 11.5,
                  fontWeight: 800,
                  cursor: 'pointer',
                  whiteSpace: 'nowrap',
                }}
              >
                📝 一時保存 (下書き)
              </button>
              <button
                onClick={() => {
                  if (
                    publishAssignedModels.length === 0 &&
                    selectedProduct?.search_model_no
                  ) {
                    setPublishAssignedModels([selectedProduct.search_model_no]);
                  }
                  setShowPublishModal(true);
                }}
                disabled={savingTemplate}
                style={{
                  background: '#EA5514',
                  color: '#FFFFFF',
                  border: 'none',
                  borderRadius: 6,
                  padding: '6px 13px',
                  fontSize: 12,
                  fontWeight: 900,
                  cursor: 'pointer',
                  whiteSpace: 'nowrap',
                  boxShadow: '0 2px 6px rgba(234, 85, 20, 0.35)',
                }}
              >
                🚀 公開して標準スタジオに反映
              </button>
            </div>
          </div>

          {/* Interactive Canvas Area */}
          <div
            style={{
              flex: 1,
              overflow: 'auto',
              padding: 24,
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              background:
                'radial-gradient(#94A3B8 1px, transparent 1px) 0 0 / 16px 16px #E2E8F0',
            }}
          >
            <div
              style={{
                marginBottom: 10,
                background: '#FFFFFF',
                padding: '5px 14px',
                borderRadius: 20,
                fontSize: 12,
                fontWeight: 800,
                color: '#1E293B',
                boxShadow: '0 2px 6px rgba(0,0,0,0.08)',
              }}
            >
              💡 枠をドラッグして移動・右下角でサイズ変更 ／ 右ペインの項目を枠へドラッグ＆ドロップまたは出力先プルダウンで即座に配置変更できます
            </div>

            <div
              style={{
                transform: `scale(${zoom})`,
                transformOrigin: 'top center',
                transition: 'transform 0.12s ease',
              }}
            >
              <DynamicBannerCanvas
                template={currentTemplate}
                specs={liveSpecs}
                fields={allFields}
                canvasRef={dynamicCanvasRef}
                selectedBoxId={selectedBoxId}
                selectedHeaderSlot={selectedHeaderSlot}
                highlightedFieldKey={highlightedFieldKey}
                showGrid={showGrid}
                overlayOpacity={overlayOpacity}
                interactive={true}
                onSelectBox={(id) => {
                  setSelectedBoxId(id);
                  if (id) {
                    const b = currentTemplate.boxes.find((x) => x.id === id);
                    if (b) setHighlightedFieldKey(b.binding.field_key);
                  }
                }}
                onSelectHeaderSlot={(slot) => setSelectedHeaderSlot(slot)}
                onUpdateBox={updateBox}
                onBindFieldToBox={bindFieldToBox}
                onBindFieldToHeaderSlot={bindFieldToHeaderSlot}
              />
            </div>
          </div>
        </main>

        {/* RIGHT PANE: Field-to-Banner Mapping & Box Property Inspector */}
        <aside
          style={{
            background: '#FFFFFF',
            borderLeft: '1px solid #CBD5E1',
            display: 'flex',
            flexDirection: 'column',
            height: 'calc(100vh - 106px)',
          }}
        >
          {/* Tabs */}
          <div style={{ display: 'flex', borderBottom: '1px solid #CBD5E1' }}>
            <button
              onClick={() => setRightTab('mapping')}
              style={{
                flex: 1,
                padding: '11px 8px',
                background: rightTab === 'mapping' ? '#FFFFFF' : '#F8FAFC',
                color: rightTab === 'mapping' ? '#4F46E5' : '#475569',
                border: 'none',
                borderBottom: rightTab === 'mapping' ? '3px solid #4F46E5' : 'none',
                fontSize: 12.5,
                fontWeight: 900,
                cursor: 'pointer',
              }}
            >
              🔗 項目マッピング＆出力位置指定
            </button>
            <button
              onClick={() => setRightTab('box_editor')}
              style={{
                flex: 1,
                padding: '11px 8px',
                background: rightTab === 'box_editor' ? '#FFFFFF' : '#F8FAFC',
                color: rightTab === 'box_editor' ? '#4F46E5' : '#475569',
                border: 'none',
                borderBottom: rightTab === 'box_editor' ? '3px solid #4F46E5' : 'none',
                fontSize: 12.5,
                fontWeight: 900,
                cursor: 'pointer',
              }}
            >
              📐 選択中の枠（フレーム）編集
            </button>
          </div>

          {rightTab === 'mapping' ? (
            <div style={{ flex: 1, overflowY: 'auto', padding: 12 }}>
              <div
                style={{
                  background: '#FEF2F2',
                  border: '1px solid #FECACA',
                  borderRadius: 8,
                  padding: '8px 10px',
                  fontSize: 11.5,
                  color: '#991B1B',
                  fontWeight: 700,
                  marginBottom: 10,
                  lineHeight: 1.4,
                }}
              >
                🎯 各項目の「🎯 メイン画面の出力先」プルダウンを変更するか、項目カードを左のバナー上の好きな枠へドラッグ＆ドロップすると、出力位置を自由に入れ替えられます！
              </div>

              {/* Add Custom Spec Field Box */}
              <div
                style={{
                  background: '#F8FAFC',
                  border: '1px solid #CBD5E1',
                  borderRadius: 8,
                  padding: 10,
                  marginBottom: 12,
                }}
              >
                <div style={{ fontSize: 11.5, fontWeight: 900, color: '#0F172A', marginBottom: 6 }}>
                  ＋ 新しいスペック項目を追加（自由項目）
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 56px 68px 52px', gap: 4 }}>
                  <input
                    type="text"
                    placeholder="項目名(例: 保証)"
                    value={newFieldLabel}
                    onChange={(e) => setNewFieldLabel(e.target.value)}
                    style={{
                      width: '100%',
                      minWidth: 0,
                      boxSizing: 'border-box',
                      padding: '5px 6px',
                      fontSize: 11.5,
                      borderRadius: 4,
                      border: '1px solid #CBD5E1',
                    }}
                  />
                  <input
                    type="text"
                    placeholder="単位"
                    value={newFieldUnit}
                    onChange={(e) => setNewFieldUnit(e.target.value)}
                    style={{
                      width: '100%',
                      minWidth: 0,
                      boxSizing: 'border-box',
                      padding: '5px 6px',
                      fontSize: 11.5,
                      borderRadius: 4,
                      border: '1px solid #CBD5E1',
                    }}
                  />
                  <input
                    type="text"
                    placeholder="初期値"
                    value={newFieldValue}
                    onChange={(e) => setNewFieldValue(e.target.value)}
                    style={{
                      width: '100%',
                      minWidth: 0,
                      boxSizing: 'border-box',
                      padding: '5px 6px',
                      fontSize: 11.5,
                      borderRadius: 4,
                      border: '1px solid #CBD5E1',
                    }}
                  />
                  <button
                    onClick={handleAddCustomField}
                    style={{
                      background: '#0F172A',
                      color: '#FFFFFF',
                      border: 'none',
                      borderRadius: 5,
                      padding: '5px 6px',
                      fontSize: 11.5,
                      fontWeight: 800,
                      cursor: 'pointer',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    追加
                  </button>
                </div>
              </div>

              {/* Field Cards with Destination Selector */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {allFields.map((field) => {
                  const currentDest = findWhereFieldIsBound(field.key);
                  const isHighlighted = highlightedFieldKey === field.key;
                  return (
                    <div
                      key={field.key}
                      draggable
                      onDragStart={(e) => {
                        e.dataTransfer.setData('text/field_key', field.key);
                        e.dataTransfer.setData('text/field_label', field.label);
                        setHighlightedFieldKey(field.key);
                      }}
                      onMouseEnter={() => setHighlightedFieldKey(field.key)}
                      onMouseLeave={() => setHighlightedFieldKey(null)}
                      style={{
                        background: isHighlighted ? '#FFF1F2' : '#FFFFFF',
                        border: isHighlighted ? '2px solid #E11D48' : '1px solid #CBD5E1',
                        borderRadius: 8,
                        padding: '8px 10px',
                        cursor: 'grab',
                        transition: 'all 0.12s',
                      }}
                    >
                      <div
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'space-between',
                          gap: 6,
                          marginBottom: 6,
                        }}
                      >
                        <div style={{ fontSize: 12, fontWeight: 900, color: '#0F172A' }}>
                          ⠿ {field.label}{' '}
                          {field.unit ? (
                            <span style={{ fontSize: 10.5, color: '#64748B' }}>({field.unit})</span>
                          ) : null}
                        </div>

                        {/* Output Destination Selector */}
                        <select
                          value={currentDest}
                          onChange={(e) => handleAssignFieldDestination(field, e.target.value)}
                          style={{
                            background: currentDest ? '#DC2626' : '#E2E8F0',
                            color: currentDest ? '#FFFFFF' : '#334155',
                            border: 'none',
                            borderRadius: 5,
                            padding: '3px 7px',
                            fontSize: 11,
                            fontWeight: 800,
                            cursor: 'pointer',
                            maxWidth: 210,
                          }}
                        >
                          <option value="" style={{ background: '#FFF', color: '#333' }}>
                            ⚪ 未出力（出力先を選択...）
                          </option>
                          {currentTemplate.boxes
                            .filter((b) => b.box_type === 'header_banner')
                            .map((hb) => (
                              <optgroup
                                key={hb.id}
                                label={`🎨 ヘッダーバナー枠 (${hb.title})`}
                                style={{ background: '#FFF', color: '#111' }}
                              >
                                <option value={`box:${hb.id}`}>
                                  🎯 ヘッダー左タイトル枠 ({hb.id})
                                </option>
                                <option value={`hbox:${hb.id}:0`}>
                                  🎯 ヘッダー右上①（メーカー等）
                                </option>
                                <option value={`hbox:${hb.id}:1`}>
                                  🎯 ヘッダー右上②（ブランド等）
                                </option>
                                <option value={`hbox:${hb.id}:2`}>
                                  🎯 ヘッダー右下（型番等）
                                </option>
                              </optgroup>
                            ))}
                          <optgroup label="🧱 メイン画面の枠（ボックス）へ出力" style={{ background: '#FFF', color: '#111' }}>
                            {currentTemplate.boxes
                              .filter((b) => b.box_type !== 'header_banner')
                              .map((b) => (
                                <option key={b.id} value={`box:${b.id}`}>
                                  🎯 枠: {b.title} ({b.id})
                                </option>
                              ))}
                          </optgroup>
                          <optgroup label="✨ 新規枠作成" style={{ background: '#FFF', color: '#111' }}>
                            <option value="__new_box__">＋ この項目用の新しい枠を追加して出力</option>
                          </optgroup>
                        </select>
                      </div>

                      {/* Spec Value Input */}
                      {field.type === 'select' && field.choices ? (
                        <select
                          value={String(liveSpecs[field.key] ?? field.default ?? '')}
                          onChange={(e) =>
                            setLiveSpecs((prev) => ({ ...prev, [field.key]: e.target.value }))
                          }
                          style={{
                            width: '100%',
                            padding: '5px 8px',
                            borderRadius: 5,
                            border: '1px solid #CBD5E1',
                            fontSize: 12,
                            fontWeight: 700,
                          }}
                        >
                          {field.choices.map((ch) => (
                            <option key={ch} value={ch}>
                              {ch}
                            </option>
                          ))}
                        </select>
                      ) : (
                        <input
                          type="text"
                          value={String(liveSpecs[field.key] ?? '')}
                          onChange={(e) =>
                            setLiveSpecs((prev) => ({ ...prev, [field.key]: e.target.value }))
                          }
                          style={{
                            width: '100%',
                            padding: '5px 8px',
                            borderRadius: 5,
                            border: '1px solid #CBD5E1',
                            fontSize: 12,
                            fontWeight: 700,
                            boxSizing: 'border-box',
                          }}
                        />
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          ) : (
            /* Tab 2: Selected Box Frame & Widget Inspector */
            <div style={{ flex: 1, overflowY: 'auto', padding: 14 }}>
              {selectedBox ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                  <div
                    style={{
                      background: '#EFF6FF',
                      border: '1px solid #BFDBFE',
                      borderRadius: 8,
                      padding: 10,
                    }}
                  >
                    <div style={{ fontSize: 13, fontWeight: 900, color: '#1E3A8A' }}>
                      📐 選択中の枠: {selectedBox.title} (<code>{selectedBox.id}</code>)
                    </div>
                    <div style={{ fontSize: 11, color: '#1D4ED8', marginTop: 2 }}>
                      位置 (X={selectedBox.x}px, Y={selectedBox.y}px) ／ サイズ ({selectedBox.w}px × {selectedBox.h}px)
                    </div>
                  </div>

                  <div>
                    <label style={{ fontSize: 11.5, fontWeight: 800 }}>① この枠に出力するスペック項目</label>
                    <select
                      value={selectedBox.binding.field_key}
                      onChange={(e) => bindFieldToBox(selectedBox.id, e.target.value)}
                      style={{
                        width: '100%',
                        padding: '7px 8px',
                        borderRadius: 6,
                        border: '2px solid #2563EB',
                        fontSize: 12.5,
                        fontWeight: 800,
                        marginTop: 4,
                      }}
                    >
                      {allFields.map((f) => (
                        <option key={f.key} value={f.key}>
                          {f.label} ({f.key}) — 現在値: {String(liveSpecs[f.key] ?? '')}
                        </option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label style={{ fontSize: 11.5, fontWeight: 800 }}>② 枠のテンプレート種別（ウィジェット）</label>
                    <select
                      value={selectedBox.box_type}
                      onChange={(e) =>
                        updateBox(selectedBox.id, { box_type: e.target.value as WidgetBoxType })
                      }
                      style={{
                        width: '100%',
                        padding: '7px 8px',
                        borderRadius: 6,
                        border: '1px solid #CBD5E1',
                        fontSize: 12,
                        fontWeight: 700,
                        marginTop: 4,
                      }}
                    >
                      {WIDGET_TYPES.map((wt) => (
                        <option key={wt.value} value={wt.value}>
                          {wt.label}
                        </option>
                      ))}
                    </select>
                  </div>

                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
                    <div>
                      <label style={{ fontSize: 11.5, fontWeight: 800 }}>見出しタイトル名</label>
                      <input
                        type="text"
                        value={selectedBox.title}
                        onChange={(e) =>
                          updateBox(selectedBox.id, {
                            title: e.target.value,
                            binding: { ...selectedBox.binding, label_override: e.target.value },
                          })
                        }
                        style={{
                          width: '100%',
                          padding: '6px 8px',
                          borderRadius: 5,
                          border: '1px solid #CBD5E1',
                          fontSize: 12,
                          boxSizing: 'border-box',
                          marginTop: 4,
                        }}
                      />
                    </div>
                    <div>
                      <label style={{ fontSize: 11.5, fontWeight: 800 }}>単位表記（任意）</label>
                      <input
                        type="text"
                        value={selectedBox.binding.unit_override || ''}
                        onChange={(e) =>
                          updateBox(selectedBox.id, {
                            binding: {
                              ...selectedBox.binding,
                              unit_override: e.target.value || null,
                            },
                          })
                        }
                        placeholder="例: V型, L, cm, GB"
                        style={{
                          width: '100%',
                          padding: '6px 8px',
                          borderRadius: 5,
                          border: '1px solid #CBD5E1',
                          fontSize: 12,
                          boxSizing: 'border-box',
                          marginTop: 4,
                        }}
                      />
                    </div>
                  </div>

                  {/* Geometry X, Y, W, H */}
                  <div>
                    <label style={{ fontSize: 11.5, fontWeight: 800 }}>③ 枠の座標・サイズ (px)</label>
                    <div
                      style={{
                        display: 'grid',
                        gridTemplateColumns: '1fr 1fr 1fr 1fr',
                        gap: 6,
                        marginTop: 4,
                      }}
                    >
                      <div>
                        <span style={{ fontSize: 10.5, color: '#475569' }}>X (左端)</span>
                        <input
                          type="number"
                          value={selectedBox.x}
                          onChange={(e) =>
                            updateBox(selectedBox.id, { x: Number(e.target.value) || 0 })
                          }
                          style={{ width: '100%', padding: 5, fontSize: 12, boxSizing: 'border-box' }}
                        />
                      </div>
                      <div>
                        <span style={{ fontSize: 10.5, color: '#475569' }}>Y (上端)</span>
                        <input
                          type="number"
                          value={selectedBox.y}
                          onChange={(e) =>
                            updateBox(selectedBox.id, { y: Number(e.target.value) || 0 })
                          }
                          style={{ width: '100%', padding: 5, fontSize: 12, boxSizing: 'border-box' }}
                        />
                      </div>
                      <div>
                        <span style={{ fontSize: 10.5, color: '#475569' }}>幅 (W)</span>
                        <input
                          type="number"
                          value={selectedBox.w}
                          onChange={(e) =>
                            updateBox(selectedBox.id, { w: Math.max(40, Number(e.target.value) || 60) })
                          }
                          style={{ width: '100%', padding: 5, fontSize: 12, boxSizing: 'border-box' }}
                        />
                      </div>
                      <div>
                        <span style={{ fontSize: 10.5, color: '#475569' }}>高さ (H)</span>
                        <input
                          type="number"
                          value={selectedBox.h}
                          onChange={(e) =>
                            updateBox(selectedBox.id, { h: Math.max(32, Number(e.target.value) || 50) })
                          }
                          style={{ width: '100%', padding: 5, fontSize: 12, boxSizing: 'border-box' }}
                        />
                      </div>
                    </div>
                  </div>

                  {/* Styling */}
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 8 }}>
                    <div>
                      <label style={{ fontSize: 11, fontWeight: 700 }}>見出し帯の色</label>
                      <input
                        type="color"
                        value={selectedBox.title_bg_color || '#666666'}
                        onChange={(e) =>
                          updateBox(selectedBox.id, { title_bg_color: e.target.value })
                        }
                        style={{ width: '100%', height: 30, marginTop: 2, cursor: 'pointer' }}
                      />
                    </div>
                    <div>
                      <label style={{ fontSize: 11, fontWeight: 700 }}>
                        {selectedBox.box_type === 'header_banner' ? 'ヘッダー背景色' : '枠の背景色'}
                      </label>
                      <input
                        type="color"
                        value={selectedBox.bg_color || '#FFFFFF'}
                        onChange={(e) =>
                          updateBox(selectedBox.id, {
                            bg_color: e.target.value,
                            ...(selectedBox.box_type === 'header_banner'
                              ? { border_color: e.target.value }
                              : {}),
                          })
                        }
                        style={{ width: '100%', height: 30, marginTop: 2, cursor: 'pointer' }}
                      />
                    </div>
                    <div>
                      <label style={{ fontSize: 11, fontWeight: 700 }}>文字色</label>
                      <input
                        type="color"
                        value={selectedBox.value_color || '#111111'}
                        onChange={(e) => updateBox(selectedBox.id, { value_color: e.target.value })}
                        style={{ width: '100%', height: 30, marginTop: 2, cursor: 'pointer' }}
                      />
                    </div>
                  </div>

                  {selectedBox.box_type === 'header_banner' && (
                    <div
                      style={{
                        background: '#F8FAFC',
                        border: '1px solid #CBD5E1',
                        borderRadius: 8,
                        padding: 10,
                        display: 'flex',
                        flexDirection: 'column',
                        gap: 8,
                      }}
                    >
                      <div style={{ fontSize: 11.5, fontWeight: 900, color: '#0F172A' }}>
                        🎨 ヘッダー右側の3項目マッピング（メーカー・ブランド・型番等）
                      </div>
                      {[
                        { idx: 0, label: '右上①（例: メーカー）' },
                        { idx: 1, label: '右上②（例: ブランド/クラス）' },
                        { idx: 2, label: '右下（例: 型番/サイズ帯）' },
                      ].map((slot) => {
                        const curSub = (selectedBox.binding.sub_field_keys || [])[slot.idx] || '';
                        return (
                          <div key={slot.idx}>
                            <label style={{ fontSize: 10.5, fontWeight: 700 }}>{slot.label}</label>
                            <select
                              value={curSub}
                              onChange={(e) => {
                                const nextSub = [
                                  ...(selectedBox.binding.sub_field_keys || ['', '', '']),
                                ];
                                while (nextSub.length < 3) nextSub.push('');
                                nextSub[slot.idx] = e.target.value;
                                updateBox(selectedBox.id, {
                                  binding: {
                                    ...selectedBox.binding,
                                    sub_field_keys: nextSub,
                                  },
                                });
                              }}
                              style={{
                                width: '100%',
                                padding: '5px 8px',
                                borderRadius: 5,
                                border: '1px solid #CBD5E1',
                                fontSize: 11.5,
                                fontWeight: 700,
                                marginTop: 2,
                              }}
                            >
                              <option value="">（なし / 非表示）</option>
                              {allFields.map((f) => (
                                <option key={f.key} value={f.key}>
                                  {f.label} ({f.key}) — {String(liveSpecs[f.key] ?? '')}
                                </option>
                              ))}
                            </select>
                          </div>
                        );
                      })}
                    </div>
                  )}

                  <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                    <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, fontWeight: 700 }}>
                      <input
                        type="checkbox"
                        checked={selectedBox.show_title_bar}
                        onChange={(e) =>
                          updateBox(selectedBox.id, { show_title_bar: e.target.checked })
                        }
                      />
                      上部の見出し帯を表示する
                    </label>
                  </div>
                </div>
              ) : (
                <div style={{ color: '#64748B', fontSize: 12.5, padding: 16 }}>
                  メイン画面上の枠をクリックすると、枠のサイズ・色・出力項目・ウィジェット種別をここで細かく編集できます。
                </div>
              )}
            </div>
          )}
        </aside>
      </div>

      {/* PUBLISH & PRODUCT LINKING MODAL */}
      {showPublishModal && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(15, 23, 42, 0.58)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 60,
          }}
        >
          <div
            style={{
              background: '#FFFFFF',
              borderRadius: 12,
              width: 560,
              maxWidth: '94vw',
              maxHeight: '88vh',
              display: 'flex',
              flexDirection: 'column',
              padding: 22,
              boxShadow: '0 20px 45px rgba(0,0,0,0.28)',
            }}
          >
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                marginBottom: 12,
              }}
            >
              <h3 style={{ margin: 0, fontSize: 17, fontWeight: 900, color: '#0F172A' }}>
                🚀 テンプレートの公開 ＆ 適用する商品の指定
              </h3>
              <button
                onClick={() => setShowPublishModal(false)}
                style={{
                  background: 'none',
                  border: 'none',
                  fontSize: 20,
                  cursor: 'pointer',
                }}
              >
                ×
              </button>
            </div>

            <div
              style={{
                background: '#FFF7ED',
                border: '1px solid #FED7AA',
                borderRadius: 8,
                padding: '10px 12px',
                fontSize: 12,
                color: '#9A3412',
                fontWeight: 700,
                lineHeight: 1.45,
                marginBottom: 12,
              }}
            >
              💡 公開すると「標準 機能表スタジオ」のテンプレート選択肢にこのテンプレートが追加されます。さらに、下の設定で**どの商品にこのテンプレートを自動適用するか**を指定できます（商品マスタ自体は読み取り専用のまま保護されます）。
            </div>

            <div style={{ marginBottom: 12 }}>
              <label style={{ fontSize: 12, fontWeight: 800, display: 'block', marginBottom: 4 }}>
                公開テンプレート名 *
              </label>
              <input
                type="text"
                value={currentTemplate.name}
                onChange={(e) =>
                  setCurrentTemplate((prev) => (prev ? { ...prev, name: e.target.value } : prev))
                }
                style={{
                  width: '100%',
                  padding: '8px 10px',
                  borderRadius: 6,
                  border: '1px solid #CBD5E1',
                  fontSize: 13,
                  fontWeight: 800,
                  boxSizing: 'border-box',
                }}
              />
            </div>

            {/* Option 1: Make Category Default */}
            <label
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                padding: '10px 12px',
                background: publishAsCategoryDefault ? '#EFF6FF' : '#F8FAFC',
                border: publishAsCategoryDefault ? '2px solid #2563EB' : '1px solid #CBD5E1',
                borderRadius: 8,
                fontSize: 12.5,
                fontWeight: 800,
                cursor: 'pointer',
                marginBottom: 12,
              }}
            >
              <input
                type="checkbox"
                checked={publishAsCategoryDefault}
                onChange={(e) => setPublishAsCategoryDefault(e.target.checked)}
              />
              <span>
                🌟 カテゴリ「{currentCatDef?.name}」の全商品の標準テンプレートとして自動適用する
              </span>
            </label>

            {/* Option 2: Assign to Specific Products in this Category */}
            <div style={{ fontSize: 12, fontWeight: 800, marginBottom: 6, color: '#1E293B' }}>
              🎯 このテンプレートを紐付ける商品を選択（{currentCatDef?.name}: {publishAssignedModels.length}件選択中）:
            </div>
            <div
              style={{
                flex: 1,
                minHeight: 150,
                maxHeight: 220,
                overflowY: 'auto',
                border: '1px solid #CBD5E1',
                borderRadius: 8,
                padding: 8,
                display: 'flex',
                flexDirection: 'column',
                gap: 4,
              }}
            >
              {categoryProducts.map((p) => {
                const checked = publishAssignedModels.includes(p.search_model_no);
                return (
                  <label
                    key={p.search_model_no}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 8,
                      padding: '6px 8px',
                      borderRadius: 6,
                      background: checked ? '#FEF2F2' : '#FFFFFF',
                      border: checked ? '1px solid #FCA5A5' : '1px solid #F1F5F9',
                      fontSize: 12,
                      fontWeight: 700,
                      cursor: 'pointer',
                    }}
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={(e) => {
                        if (e.target.checked) {
                          setPublishAssignedModels((prev) => [...prev, p.search_model_no]);
                        } else {
                          setPublishAssignedModels((prev) =>
                            prev.filter((m) => m !== p.search_model_no)
                          );
                        }
                      }}
                    />
                    <span style={{ fontWeight: 900, color: '#0F172A' }}>{p.search_model_no}</span>
                    <span style={{ color: '#475569' }}>
                      ({p.maker_name || p.specs?.maker} / {p.product_name})
                    </span>
                  </label>
                );
              })}
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 14 }}>
              <button
                type="button"
                onClick={() => setShowPublishModal(false)}
                style={{
                  background: '#F1F5F9',
                  color: '#334155',
                  border: '1px solid #CBD5E1',
                  borderRadius: 6,
                  padding: '8px 14px',
                  fontSize: 12.5,
                  fontWeight: 700,
                  cursor: 'pointer',
                }}
              >
                キャンセル
              </button>
              <button
                type="button"
                disabled={savingTemplate}
                onClick={() =>
                  handleSaveTemplate(
                    'published',
                    publishAsCategoryDefault,
                    publishAssignedModels
                  )
                }
                style={{
                  background: '#EA5514',
                  color: '#FFFFFF',
                  border: 'none',
                  borderRadius: 6,
                  padding: '8px 18px',
                  fontSize: 13,
                  fontWeight: 900,
                  cursor: 'pointer',
                }}
              >
                {savingTemplate ? '公開処理中...' : '🚀 この設定で公開する'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
