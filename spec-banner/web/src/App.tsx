import React, { useEffect, useRef, useState } from 'react';
import { toPng } from 'html-to-image';
import {
  CategoryDefinition,
  CategoryField,
  CategoryId,
  DOOR_IMAGE_MAP,
  EmailLogItem,
  ProductItem,
  TemplateSchema,
} from './types';
import { BannerCanvas } from './components/BannerCanvas';
import { DOOR_LAYOUT_PRESETS } from './components/templates/DoorDiagram3D';
import { TemplateDesignerView } from './components/TemplateDesignerView';

const CATEGORY_ICONS: Record<string, string> = {
  all: '🗂️',
  tv: '📺',
  pc: '💻',
  wine_cellar: '🍷',
  cooler_warmer: '🧊',
  freezer: '❄️',
  refrigerator: '🚪',
};

const SPECIMEN_BY_CATEGORY: Record<CategoryId, { label: string; src: string }[]> = {
  tv: [
    { label: 'Mini LED (緑ヘッダー)', src: '/assets/specimens/sample_tv_banner.png' },
    { label: '2K/4K液晶・有機ELヘッダー', src: '/assets/specimens/sample_tv_headers.png' },
  ],
  pc: [
    { label: 'FMV + e angle Select', src: '/assets/specimens/sample_pc_banner.png' },
  ],
  wine_cellar: [
    { label: 'アイリスオーヤマ IWCP081AB', src: '/assets/specimens/sample_wine_banner.png' },
  ],
  cooler_warmer: [
    { label: 'VERSOS VS442', src: '/assets/specimens/sample_cooler_banner.png' },
  ],
  freezer: [
    { label: '1ドア AQUA AQFSF11R', src: '/assets/specimens/sample_freezer_1door.png' },
    { label: '2ドア 三菱 MFU22KW', src: '/assets/specimens/sample_freezer_2door.png' },
  ],
  refrigerator: [
    { label: '350L以上 (緑) TOSHIBA GRA600XFS', src: '/assets/specimens/sample_fridge_large.png' },
    { label: '349L以下 (水色) HITACHI R27XN', src: '/assets/specimens/sample_fridge_small.png' },
  ],
};

export const App: React.FC = () => {
  // Check if opened by server-side Headless Chromium for pixel-exact JPEG/PDF export
  const isRenderMode =
    typeof window !== 'undefined' &&
    new URLSearchParams(window.location.search).get('renderMode') === '1';

  const [categories, setCategories] = useState<CategoryDefinition[]>([]);
  const [products, setProducts] = useState<ProductItem[]>([]);
  const [selectedCategory, setSelectedCategory] = useState<string>('all');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [selectedProduct, setSelectedProduct] = useState<ProductItem | null>(null);
  const [liveSpecs, setLiveSpecs] = useState<Record<string, any>>({});
  const [liveCategory, setLiveCategory] = useState<CategoryId>('tv');
  const [renderReady, setRenderReady] = useState<boolean>(false);
  const [zoom, setZoom] = useState<number>(1.0);
  const [showSpecimenCompare, setShowSpecimenCompare] = useState<boolean>(false);
  const [specimenIndex, setSpecimenIndex] = useState<number>(0);
  const [rightTab, setRightTab] = useState<'specs' | 'master' | 'mail_logs'>('specs');
  const [appMode, setAppMode] = useState<'standard' | 'designer'>('standard');
  const [publishedTemplates, setPublishedTemplates] = useState<TemplateSchema[]>([]);
  const [activeTemplateVariant, setActiveTemplateVariant] = useState<string>('auto');

  // Status & Loading states
  const [loading, setLoading] = useState<boolean>(false);
  const [saving, setSaving] = useState<boolean>(false);
  const [aiEnriching, setAiEnriching] = useState<boolean>(false);
  const [exporting, setExporting] = useState<boolean>(false);
  const [toast, setToast] = useState<{ type: 'success' | 'info' | 'error'; text: string } | null>(
    null
  );

  // Modals
  const [showEmailModal, setShowEmailModal] = useState<boolean>(false);
  const [emailTo, setEmailTo] = useState<string>('vmd-team@cymbal-retail.example.com');
  const [emailCc, setEmailCc] = useState<string>('');
  const [emailSubject, setEmailSubject] = useState<string>('');
  const [emailBody, setEmailBody] = useState<string>('');
  const [emailFormat, setEmailFormat] = useState<'jpeg' | 'pdf' | 'both'>('both');
  const [sendingEmail, setSendingEmail] = useState<boolean>(false);
  const [lastSentResult, setLastSentResult] = useState<any | null>(null);
  const [emailLogs, setEmailLogs] = useState<EmailLogItem[]>([]);

  const [showNewModal, setShowNewModal] = useState<boolean>(false);
  const [newCat, setNewCat] = useState<CategoryId>('tv');
  const [newJan, setNewJan] = useState<string>('');
  const [newModel, setNewModel] = useState<string>('');
  const [newMaker, setNewMaker] = useState<string>('');
  const [newName, setNewName] = useState<string>('');
  const [newPrice, setNewPrice] = useState<string>('128000');

  const bannerRef = useRef<HTMLDivElement | null>(null);
  const excelInputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    if (isRenderMode) {
      (window as any).__setRenderPayload = (payload: {
        category: CategoryId;
        specs: Record<string, any>;
      }) => {
        setLiveCategory(payload.category || 'tv');
        setLiveSpecs(payload.specs || {});
        setRenderReady(true);
      };
      return;
    }
    fetchInitialData();
  }, [isRenderMode]);

  const applyDoorLayoutChange = (newLayout: string) => {
    const preset = DOOR_LAYOUT_PRESETS[newLayout];
    if (!preset) {
      setLiveSpecs((prev) => ({ ...prev, door_layout: newLayout }));
      return;
    }
    setLiveSpecs((prev) => {
      const next: Record<string, any> = {
        ...prev,
        door_layout: newLayout,
        door_count: preset.doorCount,
      };
      const totalCap = parseFloat(String(prev.capacity_l || '200')) || 200;
      for (let i = 1; i <= 6; i++) {
        if (i <= preset.roomCount) {
          const defRoom = preset.defaultRooms[i - 1] || { name: '冷凍室', ratio: 0.2 };
          const curName = String(prev[`comp${i}_name`] || '').trim();
          const curCap = String(prev[`comp${i}_capacity_l`] || '').trim();
          if (!curName || curName === '-') {
            next[`comp${i}_name`] = defRoom.name;
          }
          if (!curCap || preset.roomCount === 1) {
            const estCap =
              preset.roomCount === 1
                ? Math.round(totalCap)
                : Math.max(8, Math.round(totalCap * defRoom.ratio));
            next[`comp${i}_capacity_l`] = estCap;
            next[`comp${i}_food_space_l`] = Math.max(5, Math.round(estCap * 0.68));
          }
        } else {
          next[`comp${i}_name`] = '';
          next[`comp${i}_capacity_l`] = '';
          next[`comp${i}_food_space_l`] = '';
        }
      }
      return next;
    });
  };

  const showToastMsg = (text: string, type: 'success' | 'info' | 'error' = 'success') => {
    setToast({ type, text });
    setTimeout(() => {
      setToast((prev) => (prev?.text === text ? null : prev));
    }, 5000);
  };

  const fetchInitialData = async (preserveId?: number | string) => {
    setLoading(true);
    try {
      const [catRes, prodRes, logRes, tplRes] = await Promise.all([
        fetch('/api/categories'),
        fetch('/api/products'),
        fetch('/api/email/logs'),
        fetch('/api/templates?only_published=true'),
      ]);
      const catData = await catRes.json();
      const prodData = await prodRes.json();
      const logData = await logRes.json();
      const tplData = await tplRes.json();

      setCategories(catData.categories || []);
      const items: ProductItem[] = prodData.items || [];
      setProducts(items);
      setEmailLogs(logData.items || []);
      const pubTpls: TemplateSchema[] = (tplData.items || []).filter(
        (t: TemplateSchema) => !t.is_preset && t.status === 'published'
      );
      setPublishedTemplates(pubTpls);

      if (items.length > 0) {
        const target =
          (preserveId &&
            items.find(
              (p) =>
                p.id === preserveId ||
                p.jan_code === preserveId ||
                p.search_model_no === preserveId
            )) ||
          items[0];
        selectProductItem(target, pubTpls);
      }
    } catch (err: any) {
      showToastMsg(`データ取得エラー: ${err.message}`, 'error');
    } finally {
      setLoading(false);
    }
  };

  const selectProductItem = (item: ProductItem, pubListOverride?: TemplateSchema[]) => {
    setSelectedProduct(item);
    setLiveCategory(item.category);
    const pubList = pubListOverride || publishedTemplates;

    // Resolve if a published custom template is assigned to this product or set as category default
    const matchedTpl =
      pubList.find((t) => t.template_id === item.template_variant) ||
      pubList.find(
        (t) =>
          t.category === item.category &&
          (t.assigned_models || []).includes(item.search_model_no)
      ) ||
      pubList.find((t) => t.category === item.category && t.is_category_default);

    setActiveTemplateVariant(matchedTpl ? matchedTpl.template_id : 'auto');

    const nextSpecs = { ...(item.specs || {}) };
    if (matchedTpl && matchedTpl.custom_fields) {
      for (const cf of matchedTpl.custom_fields) {
        if (nextSpecs[cf.key] === undefined && cf.default !== undefined) {
          nextSpecs[cf.key] = cf.default;
        }
      }
    }
    setLiveSpecs(nextSpecs);
    setSpecimenIndex(0);
    setLastSentResult(null);
    setEmailSubject(
      `【Cymbal VMD】${item.maker_name || item.specs?.maker || ''} ${item.search_model_no} 機能表（POPバナー）送付のご案内`
    );
    setEmailBody(
      `お疲れ様です。\nCymbal Retail VMD 機能表・POP自動生成スタジオより、下記商品の店舗展示用機能表（ディスプレイバナー）データを添付にてお送りいたします。\n\n・カテゴリ: ${item.category_name}\n・メーカー: ${item.maker_name || item.specs?.maker || ''}\n・型番: ${item.search_model_no}\n・JANコード: ${item.jan_code}\n・Cymbal 売価: ¥${(item.edion_price || 0).toLocaleString()} (税込)\n\nご確認のほどよろしくお願いいたします。`
    );
  };

  const filteredProducts = products.filter((p) => {
    if (selectedCategory !== 'all' && p.category !== selectedCategory) return false;
    if (searchQuery.trim() !== '') {
      const q = searchQuery.trim().toLowerCase();
      const match =
        (p.jan_code || '').toLowerCase().includes(q) ||
        (p.search_model_no || '').toLowerCase().includes(q) ||
        (p.maker_name || '').toLowerCase().includes(q) ||
        (p.product_name || '').toLowerCase().includes(q) ||
        (p.specs?.maker || '').toLowerCase().includes(q);
      if (!match) return false;
    }
    return true;
  });

  const currentCatDef = categories.find((c) => c.id === liveCategory);

  const captureBannerDataUrl = async (): Promise<string | null> => {
    if (!bannerRef.current) return null;
    try {
      if (document.fonts && document.fonts.ready) {
        await document.fonts.ready;
      }
      const dataUrl = await toPng(bannerRef.current, {
        pixelRatio: 3.0,
        backgroundColor: '#FFFFFF',
        cacheBust: true,
      });
      return dataUrl;
    } catch (e) {
      console.warn('Frontend html-to-image capture fell back to server renderer:', e);
      return null;
    }
  };

  const handleSaveSpecs = async () => {
    if (!selectedProduct) return;
    setSaving(true);
    try {
      const dataUrl = await captureBannerDataUrl();
      const ident =
        selectedProduct.search_model_no ||
        selectedProduct.jan_code ||
        String(selectedProduct.id);
      const res = await fetch(`/api/products/${encodeURIComponent(ident)}/specs`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          category: liveCategory,
          template_variant: activeTemplateVariant,
          specs: liveSpecs,
          image_data_url: dataUrl,
        }),
      });
      if (!res.ok) throw new Error('バナー保存に失敗しました');
      const updated: ProductItem = await res.json();
      setProducts((prev) =>
        prev.map((p) => (p.search_model_no === updated.search_model_no ? updated : p))
      );
      setSelectedProduct(updated);
      showToastMsg(
        `「${updated.search_model_no}」のバナー画像・設定を GCS & BigQuery に保存しました（商品マスタは読み取り専用）`
      );
    } catch (err: any) {
      showToastMsg(err.message, 'error');
    } finally {
      setSaving(false);
    }
  };

  const handleAiEnrich = async () => {
    if (!selectedProduct) return;
    setAiEnriching(true);
    showToastMsg('Vertex AI Gemini 2.5 Flash + Google 検索でメーカー仕様を取得中...', 'info');
    try {
      const ident = selectedProduct.jan_code || selectedProduct.search_model_no || String(selectedProduct.id);
      const res = await fetch(
        `/api/products/${encodeURIComponent(ident)}/ai-enrich?category=${liveCategory}`,
        { method: 'POST' }
      );
      if (!res.ok) throw new Error('AI自動補完に失敗しました');
      const data = await res.json();
      const updated: ProductItem = data.product;
      setProducts((prev) =>
        prev.map((p) => (p.search_model_no === updated.search_model_no ? updated : p))
      );
      setSelectedProduct(updated);
      setLiveSpecs({ ...(updated.specs || {}) });
      showToastMsg('✨ Gemini 2.5 Flash による機能表スペック自動補完が完了しました！');
    } catch (err: any) {
      showToastMsg(err.message, 'error');
    } finally {
      setAiEnriching(false);
    }
  };

  const handleSyncMaster = async () => {
    setLoading(true);
    try {
      const res = await fetch('/api/sync-master', { method: 'POST' });
      const data = await res.json();
      await fetchInitialData(selectedProduct?.search_model_no);
      showToastMsg(
        `商品マスタと同期完了（全${data.master_total}件 / 新規連携${data.auto_created_kinohyo}件）`
      );
    } catch (err: any) {
      showToastMsg(err.message, 'error');
    } finally {
      setLoading(false);
    }
  };

  const handleExcelUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setLoading(true);
    try {
      const fd = new FormData();
      fd.append('file', file);
      const res = await fetch('/api/import-excel', {
        method: 'POST',
        body: fd,
      });
      if (!res.ok) throw new Error('Excelの取込に失敗しました');
      const data = await res.json();
      await fetchInitialData(data.items?.[0]?.search_model_no);
      setSelectedCategory(data.detected_category);
      showToastMsg(
        `「${file.name}」から ${data.imported_count} 件の${data.detected_category.toUpperCase()}機能表データを一括取込しました！`
      );
    } catch (err: any) {
      showToastMsg(err.message, 'error');
    } finally {
      setLoading(false);
      if (excelInputRef.current) excelInputRef.current.value = '';
    }
  };

  const handleExportJpeg = async () => {
    if (!selectedProduct) return;
    setExporting(true);
    showToastMsg('高解像度JPEG (300 DPI) をレンダリング中...', 'info');
    try {
      const modelNo = String(liveSpecs.model_no || selectedProduct.search_model_no || 'banner').replace(
        /\//g,
        '_'
      );
      const filename = `Cymbal_機能表_${modelNo}.jpg`;

      const dataUrl = await captureBannerDataUrl();
      const res = await fetch('/api/export/jpeg', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          product_id: selectedProduct.search_model_no,
          jan_code: selectedProduct.jan_code,
          category: liveCategory,
          specs: liveSpecs,
          image_data_url: dataUrl,
          filename,
        }),
      });
      if (!res.ok) throw new Error('JPEG生成に失敗しました');
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      showToastMsg(`高解像度JPEG (${filename}) をダウンロードしました`);
    } catch (err: any) {
      showToastMsg(err.message, 'error');
    } finally {
      setExporting(false);
    }
  };

  const handleExportPdf = async () => {
    if (!selectedProduct) return;
    setExporting(true);
    showToastMsg('印刷用PDF (A4・高精細) をレンダリング中...', 'info');
    try {
      const modelNo = String(liveSpecs.model_no || selectedProduct.search_model_no || 'banner').replace(
        /\//g,
        '_'
      );
      const filename = `Cymbal_機能表_${modelNo}.pdf`;

      const dataUrl = await captureBannerDataUrl();
      const res = await fetch('/api/export/pdf', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          product_id: selectedProduct.search_model_no,
          jan_code: selectedProduct.jan_code,
          category: liveCategory,
          specs: liveSpecs,
          image_data_url: dataUrl,
          filename,
        }),
      });
      if (!res.ok) throw new Error('PDF生成に失敗しました');
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      showToastMsg(`印刷用PDF (${filename}) をダウンロードしました`);
    } catch (err: any) {
      showToastMsg(err.message, 'error');
    } finally {
      setExporting(false);
    }
  };

  const handleSendEmail = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedProduct || !emailTo.trim()) return;
    setSendingEmail(true);
    try {
      const dataUrl = await captureBannerDataUrl();
      const res = await fetch('/api/email/send', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          to_email: emailTo.trim(),
          cc_email: emailCc.trim() || null,
          subject: emailSubject,
          body: emailBody,
          attachment_format: emailFormat,
          product_id: selectedProduct.product_id,
          jan_code: selectedProduct.jan_code,
          search_model_no: selectedProduct.search_model_no,
          category: liveCategory,
          specs: liveSpecs,
          image_data_url: dataUrl,
        }),
      });
      if (!res.ok) throw new Error('メール送信リクエストに失敗しました');
      const result = await res.json();
      setLastSentResult(result);
      const logRes = await fetch('/api/email/logs');
      const logData = await logRes.json();
      setEmailLogs(logData.items || []);
      showToastMsg(
        `メール送信完了（宛先: ${result.to_email} / ステータス: ${result.status}）`
      );
    } catch (err: any) {
      showToastMsg(err.message, 'error');
    } finally {
      setSendingEmail(false);
    }
  };

  const handleCreateProduct = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newJan.trim() || !newModel.trim()) return;
    setSaving(true);
    try {
      const res = await fetch('/api/products', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          category: newCat,
          jan_code: newJan.trim(),
          search_model_no: newModel.trim(),
          maker_name: newMaker.trim() || 'SONY',
          product_name: newName.trim() || newModel.trim(),
          edion_price: parseInt(newPrice, 10) || 98000,
          specs: {
            maker: newMaker.trim() || 'SONY',
            model_no: newModel.trim(),
            jan_code: newJan.trim(),
          },
        }),
      });
      if (!res.ok) throw new Error('新規商品作成に失敗しました');
      const created: ProductItem = await res.json();
      setShowNewModal(false);
      await fetchInitialData(created.search_model_no);
      showToastMsg(`新規商品「${created.search_model_no}」を商品マスタ＆機能表に登録しました`);
    } catch (err: any) {
      showToastMsg(err.message, 'error');
    } finally {
      setSaving(false);
    }
  };

  const activePublishedTemplate = React.useMemo(() => {
    if (!activeTemplateVariant || activeTemplateVariant === 'auto') return null;
    return publishedTemplates.find((t) => t.template_id === activeTemplateVariant) || null;
  }, [activeTemplateVariant, publishedTemplates]);

  // Group fields for the right-hand editor (including custom fields from an active published template)
  const groupedFields: Record<string, CategoryField[]> = {};
  if (currentCatDef) {
    const existingKeys = new Set<string>();
    for (const f of currentCatDef.fields) {
      existingKeys.add(f.key);
      if (!groupedFields[f.group]) groupedFields[f.group] = [];
      groupedFields[f.group].push(f);
    }
    if (activePublishedTemplate?.custom_fields) {
      for (const cf of activePublishedTemplate.custom_fields) {
        if (!existingKeys.has(cf.key)) {
          existingKeys.add(cf.key);
          const grp = cf.group || 'カスタム追加項目';
          if (!groupedFields[grp]) groupedFields[grp] = [];
          groupedFields[grp].push(cf);
        }
      }
    }
  }

  const specimensForCat = SPECIMEN_BY_CATEGORY[liveCategory] || [];

  // Headless Chromium clean render mode for 100% pixel-identical JPEG/PDF export
  if (isRenderMode) {
    return (
      <div
        style={{
          margin: 0,
          padding: 0,
          background: '#FFFFFF',
          display: 'inline-block',
          fontFamily: "'BIZ UDPGothic', sans-serif",
        }}
      >
        <div
          id="banner-export-target"
          data-ready={renderReady ? 'true' : 'false'}
          style={{
            display: 'inline-block',
            background: '#FFFFFF',
          }}
        >
          <BannerCanvas category={liveCategory} specs={liveSpecs} canvasRef={bannerRef} />
        </div>
      </div>
    );
  }

  return (
    <div
      style={{
        minHeight: '100vh',
        display: 'flex',
        flexDirection: 'column',
        background: '#F1F5F9',
        color: '#0F172A',
        fontFamily: "'BIZ UDPGothic', sans-serif",
      }}
    >
      {/* Top Corporate Cymbal Retail Header Bar */}
      <header
        style={{
          background: 'linear-gradient(90deg, #1557b0 0%, #1a73e8 65%, #4285f4 100%)',
          color: '#FFFFFF',
          padding: '8px 16px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 10,
          boxShadow: '0 2px 10px rgba(0,0,0,0.15)',
          zIndex: 20,
          whiteSpace: 'nowrap',
          overflowX: 'auto',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexShrink: 0 }}>
          <div
            style={{
              background: '#FFFFFF',
              padding: '4px 10px',
              borderRadius: 8,
              display: 'inline-flex',
              alignItems: 'center',
              gap: 7,
              boxShadow: '0 1px 3px rgba(0,0,0,0.12)',
              whiteSpace: 'nowrap',
            }}
          >
            <svg viewBox="0 0 40 40" width="24" height="24" aria-hidden="true">
              <defs>
                <linearGradient id="cymbalLogoGrad" x1="0" y1="0" x2="1" y2="1">
                  <stop offset="0" stopColor="#4285f4" />
                  <stop offset="1" stopColor="#1a5fd0" />
                </linearGradient>
              </defs>
              <circle cx="20" cy="20" r="19" fill="url(#cymbalLogoGrad)" />
              <circle cx="20" cy="20" r="12.5" fill="none" stroke="#fff" strokeOpacity=".55" strokeWidth="1.8" />
              <circle cx="20" cy="20" r="6.5" fill="none" stroke="#fff" strokeOpacity=".85" strokeWidth="1.8" />
              <circle cx="20" cy="20" r="2.4" fill="#fbbc04" />
            </svg>
            <span style={{ fontSize: 16, fontWeight: 800, color: '#202124', letterSpacing: '-0.02em' }}>
              Cymbal <span style={{ fontWeight: 500, color: '#5f6368' }}>Retail</span>
            </span>
          </div>
          <div style={{ whiteSpace: 'nowrap' }}>
            <div style={{ fontSize: 16, fontWeight: 900, letterSpacing: '0.02em', lineHeight: 1.2 }}>
              VMD 機能表・ディスプレイバナー自動生成スタジオ
            </div>
            <div style={{ fontSize: 10.5, opacity: 0.9, lineHeight: 1.2 }}>
              6大カテゴリ対応（テレビ・パソコン・ワインセラー・冷温庫・冷凍庫・冷蔵庫）｜商品マスタ連携・JPEG/PDF出力・メール配信
            </div>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0, whiteSpace: 'nowrap' }}>
          {/* Clean Single-Line Menu Switcher (Removed 本番完成版 / ラボ) */}
          <div
            style={{
              display: 'inline-flex',
              background: 'rgba(0, 0, 0, 0.2)',
              padding: 3,
              borderRadius: 8,
              border: '1px solid rgba(255,255,255,0.28)',
              gap: 4,
              whiteSpace: 'nowrap',
            }}
          >
            <button
              onClick={() => setAppMode('standard')}
              style={{
                background: appMode === 'standard' ? '#FFFFFF' : 'transparent',
                color: appMode === 'standard' ? '#1a73e8' : '#FFFFFF',
                border: 'none',
                borderRadius: 6,
                padding: '6px 12px',
                fontSize: 12,
                fontWeight: 900,
                cursor: 'pointer',
                whiteSpace: 'nowrap',
              }}
            >
              🏪 標準 機能表スタジオ
            </button>
            <button
              onClick={() => setAppMode('designer')}
              style={{
                background: appMode === 'designer' ? '#FACC15' : 'transparent',
                color: appMode === 'designer' ? '#1E1B4B' : '#FFFFFF',
                border: 'none',
                borderRadius: 6,
                padding: '6px 12px',
                fontSize: 12,
                fontWeight: 900,
                cursor: 'pointer',
                whiteSpace: 'nowrap',
              }}
            >
              🧩 テンプレート・項目配置デザイナー
            </button>
          </div>

          <input
            ref={excelInputRef}
            type="file"
            accept=".xlsx,.xlsm"
            style={{ display: 'none' }}
            onChange={handleExcelUpload}
          />
          <button
            onClick={() => excelInputRef.current?.click()}
            style={{
              background: '#FFFFFF',
              color: '#1a73e8',
              border: 'none',
              borderRadius: 6,
              padding: '6px 11px',
              fontSize: 12,
              fontWeight: 800,
              cursor: 'pointer',
              display: 'inline-flex',
              alignItems: 'center',
              gap: 5,
              whiteSpace: 'nowrap',
            }}
          >
            📥 機能表Excel取込 (.xlsx)
          </button>

          <button
            onClick={handleSyncMaster}
            style={{
              background: 'rgba(255,255,255,0.16)',
              color: '#FFFFFF',
              border: '1px solid rgba(255,255,255,0.4)',
              borderRadius: 6,
              padding: '6px 11px',
              fontSize: 12,
              fontWeight: 700,
              cursor: 'pointer',
              whiteSpace: 'nowrap',
            }}
          >
            🔄 商品マスタ同期
          </button>

          {selectedProduct?.registration_url &&
            !selectedProduct.registration_url.includes('edion-product-registration') && (
              <a
                href={selectedProduct.registration_url}
                target="_blank"
                rel="noreferrer"
                style={{
                  background: '#1557b0',
                  color: '#FFFFFF',
                  textDecoration: 'none',
                  border: '1px solid rgba(255,255,255,0.35)',
                  borderRadius: 6,
                  padding: '6px 11px',
                  fontSize: 12,
                  fontWeight: 800,
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 4,
                  whiteSpace: 'nowrap',
                }}
              >
                🔗 商品マスタ登録システムを開く ↗
              </a>
            )}
        </div>
      </header>

      {/* Toast Notification */}
      {toast && (
        <div
          style={{
            position: 'fixed',
            bottom: 20,
            right: 24,
            zIndex: 100,
            background:
              toast.type === 'error'
                ? '#DC2626'
                : toast.type === 'info'
                ? '#0284C7'
                : '#059669',
            color: '#FFFFFF',
            padding: '12px 18px',
            borderRadius: 8,
            fontWeight: 700,
            fontSize: 13.5,
            boxShadow: '0 10px 25px rgba(0,0,0,0.2)',
          }}
        >
          {toast.text}
        </div>
      )}

      {appMode === 'designer' ? (
        <TemplateDesignerView
          categories={categories}
          products={products}
          showToastMsg={showToastMsg}
          onTemplatesUpdated={() => fetchInitialData(selectedProduct?.search_model_no)}
        />
      ) : (
        <>
          {/* Category Filter Strip */}
          <div
            style={{
              background: '#FFFFFF',
              borderBottom: '1px solid #CBD5E1',
              padding: '8px 20px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: 12,
              flexWrap: 'wrap',
            }}
          >
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <button
            onClick={() => setSelectedCategory('all')}
            style={{
              background: selectedCategory === 'all' ? '#003E92' : '#F1F5F9',
              color: selectedCategory === 'all' ? '#FFFFFF' : '#334155',
              border: '1px solid #CBD5E1',
              borderRadius: 20,
              padding: '5px 14px',
              fontSize: 12.5,
              fontWeight: 800,
              cursor: 'pointer',
            }}
          >
            {CATEGORY_ICONS.all} すべて ({products.length})
          </button>

          {categories.map((cat) => {
            const active = selectedCategory === cat.id;
            const cnt = products.filter((p) => p.category === cat.id).length;
            return (
              <button
                key={cat.id}
                onClick={() => {
                  setSelectedCategory(cat.id);
                  const firstInCat = products.find((p) => p.category === cat.id);
                  if (firstInCat) selectProductItem(firstInCat);
                }}
                style={{
                  background: active ? '#003E92' : '#F8FAFC',
                  color: active ? '#FFFFFF' : '#1E293B',
                  border: active ? '1px solid #003E92' : '1px solid #CBD5E1',
                  borderRadius: 20,
                  padding: '5px 14px',
                  fontSize: 12.5,
                  fontWeight: 800,
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 5,
                }}
              >
                <span>{CATEGORY_ICONS[cat.id]}</span>
                <span>{cat.name}</span>
                <span
                  style={{
                    background: active ? 'rgba(255,255,255,0.22)' : '#E2E8F0',
                    color: active ? '#FFFFFF' : '#475569',
                    borderRadius: 10,
                    padding: '0 6px',
                    fontSize: 11,
                  }}
                >
                  {cnt}
                </span>
              </button>
            );
          })}
        </div>

        <button
          onClick={() => setShowNewModal(true)}
          style={{
            background: '#0F172A',
            color: '#FFFFFF',
            border: 'none',
            borderRadius: 6,
            padding: '6px 13px',
            fontSize: 12,
            fontWeight: 800,
            cursor: 'pointer',
          }}
        >
          ＋ 新規商品・機能表追加
        </button>
      </div>

      {/* Toast Notification */}
      {toast && (
        <div
          style={{
            position: 'fixed',
            bottom: 20,
            right: 24,
            zIndex: 100,
            background:
              toast.type === 'error'
                ? '#DC2626'
                : toast.type === 'info'
                ? '#0284C7'
                : '#059669',
            color: '#FFFFFF',
            padding: '12px 18px',
            borderRadius: 8,
            fontWeight: 700,
            fontSize: 13.5,
            boxShadow: '0 10px 25px rgba(0,0,0,0.2)',
          }}
        >
          {toast.text}
        </div>
      )}

      {/* Main 3-Pane Workspace */}
      <div
        style={{
          flex: 1,
          display: 'grid',
          gridTemplateColumns: '320px 1fr 410px',
          minHeight: 0,
        }}
      >
        {/* LEFT PANE: Product List */}
        <aside
          style={{
            background: '#FFFFFF',
            borderRight: '1px solid #CBD5E1',
            display: 'flex',
            flexDirection: 'column',
            height: 'calc(100vh - 108px)',
          }}
        >
          <div style={{ padding: 12, borderBottom: '1px solid #E2E8F0' }}>
            <input
              type="text"
              placeholder="🔍 型番・JANコード・メーカー・商品名で検索..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              style={{
                width: '100%',
                padding: '8px 11px',
                borderRadius: 6,
                border: '1px solid #CBD5E1',
                fontSize: 12.5,
                boxSizing: 'border-box',
              }}
            />
          </div>

          <div style={{ flex: 1, overflowY: 'auto', padding: 8 }}>
            {filteredProducts.map((item) => {
              const isSelected =
                selectedProduct?.search_model_no === item.search_model_no &&
                selectedProduct?.jan_code === item.jan_code;
              return (
                <div
                  key={`${item.jan_code}-${item.search_model_no}`}
                  onClick={() => selectProductItem(item)}
                  style={{
                    padding: '10px 12px',
                    borderRadius: 8,
                    marginBottom: 6,
                    cursor: 'pointer',
                    background: isSelected ? '#EFF6FF' : '#FFFFFF',
                    border: isSelected ? '2px solid #0055B8' : '1px solid #E2E8F0',
                    transition: 'all 0.12s',
                  }}
                >
                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      marginBottom: 4,
                    }}
                  >
                    <span
                      style={{
                        background: '#003E92',
                        color: '#FFFFFF',
                        fontSize: 10,
                        fontWeight: 800,
                        padding: '2px 7px',
                        borderRadius: 4,
                      }}
                    >
                      {CATEGORY_ICONS[item.category]} {item.category_name}
                    </span>

                    {item.linked_master && (
                      <span
                        style={{
                          background: '#DCFCE7',
                          color: '#166534',
                          fontSize: 10,
                          fontWeight: 800,
                          padding: '2px 6px',
                          borderRadius: 4,
                        }}
                      >
                        ✓ マスタ連携済
                      </span>
                    )}
                  </div>

                  <div style={{ fontSize: 11.5, color: '#475569', fontWeight: 700 }}>
                    {item.maker_name || item.specs?.maker}
                  </div>
                  <div style={{ fontSize: 15, fontWeight: 900, color: '#0F172A' }}>
                    {item.search_model_no}
                  </div>
                  <div style={{ fontSize: 12, color: '#334155', marginTop: 1 }}>
                    {item.product_name}
                  </div>

                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      marginTop: 6,
                      fontSize: 11,
                      color: '#64748B',
                    }}
                  >
                    <span>JAN: {item.jan_code}</span>
                    {item.edion_price > 0 && (
                      <span style={{ color: '#EA5514', fontWeight: 900, fontSize: 12.5 }}>
                        ¥{item.edion_price.toLocaleString()}
                      </span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </aside>

        {/* CENTER PANE: Live Display Banner Canvas & Action Toolbar */}
        <main
          style={{
            display: 'flex',
            flexDirection: 'column',
            height: 'calc(100vh - 108px)',
            overflow: 'hidden',
          }}
        >
          {/* Action Toolbar above Banner */}
          <div
            style={{
              background: '#FFFFFF',
              borderBottom: '1px solid #CBD5E1',
              padding: '10px 16px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              flexWrap: 'wrap',
              gap: 8,
            }}
          >
            {/* Left: Zoom & Specimen Comparison Toggle */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <span style={{ fontSize: 12, fontWeight: 800, color: '#475569' }}>表示倍率:</span>
              {[0.75, 1.0, 1.15].map((z) => (
                <button
                  key={z}
                  onClick={() => setZoom(z)}
                  style={{
                    background: zoom === z ? '#0F172A' : '#F1F5F9',
                    color: zoom === z ? '#FFFFFF' : '#334155',
                    border: '1px solid #CBD5E1',
                    borderRadius: 5,
                    padding: '4px 9px',
                    fontSize: 11.5,
                    fontWeight: 800,
                    cursor: 'pointer',
                  }}
                >
                  {Math.round(z * 100)}%
                </button>
              ))}

              <button
                onClick={() => setShowSpecimenCompare((prev) => !prev)}
                style={{
                  marginLeft: 6,
                  background: showSpecimenCompare ? '#7C3AED' : '#F8FAFC',
                  color: showSpecimenCompare ? '#FFFFFF' : '#475569',
                  border: '1px solid #CBD5E1',
                  borderRadius: 6,
                  padding: '5px 10px',
                  fontSize: 11.5,
                  fontWeight: 800,
                  cursor: 'pointer',
                }}
              >
                🔍 標本デザイン比較 {showSpecimenCompare ? 'ON' : 'OFF'}
              </button>
            </div>

            {/* Right: JPEG Download, PDF Download, Send Email */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <button
                onClick={handleExportJpeg}
                disabled={exporting}
                style={{
                  background: '#0284C7',
                  color: '#FFFFFF',
                  border: 'none',
                  borderRadius: 6,
                  padding: '7px 13px',
                  fontSize: 12.5,
                  fontWeight: 800,
                  cursor: 'pointer',
                }}
              >
                🖼️ JPEG ダウンロード (.jpg)
              </button>

              <button
                onClick={handleExportPdf}
                disabled={exporting}
                style={{
                  background: '#059669',
                  color: '#FFFFFF',
                  border: 'none',
                  borderRadius: 6,
                  padding: '7px 13px',
                  fontSize: 12.5,
                  fontWeight: 800,
                  cursor: 'pointer',
                }}
              >
                📄 PDF ダウンロード (.pdf)
              </button>

              <button
                onClick={() => {
                  setLastSentResult(null);
                  setShowEmailModal(true);
                }}
                style={{
                  background: '#EA5514',
                  color: '#FFFFFF',
                  border: 'none',
                  borderRadius: 6,
                  padding: '7px 14px',
                  fontSize: 12.5,
                  fontWeight: 900,
                  cursor: 'pointer',
                  boxShadow: '0 2px 6px rgba(234, 85, 20, 0.35)',
                }}
              >
                ✉️ メールに添付して送信
              </button>
            </div>
          </div>

          {/* Canvas Scroll Area */}
          <div
            style={{
              flex: 1,
              overflow: 'auto',
              padding: 24,
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              gap: 20,
              background:
                'radial-gradient(#CBD5E1 1px, transparent 1px) 0 0 / 18px 18px #E2E8F0',
            }}
          >
            {selectedProduct ? (
              <div
                style={{
                  display: 'flex',
                  gap: 24,
                  alignItems: 'flex-start',
                  flexWrap: 'wrap',
                  justifyContent: 'center',
                }}
              >
                {/* Live Rendered Display Banner */}
                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
                  <div
                    style={{
                      marginBottom: 8,
                      fontSize: 12,
                      fontWeight: 800,
                      color: '#334155',
                      background: '#FFFFFF',
                      padding: '4px 12px',
                      borderRadius: 20,
                      boxShadow: '0 1px 3px rgba(0,0,0,0.08)',
                    }}
                  >
                    🟢 リアルタイム描画バナー（{currentCatDef?.name}：{selectedProduct.search_model_no}）
                  </div>
                  <div
                    style={{
                      transform: `scale(${zoom})`,
                      transformOrigin: 'top center',
                      transition: 'transform 0.15s ease',
                    }}
                  >
                    <BannerCanvas
                      category={liveCategory}
                      specs={liveSpecs}
                      canvasRef={bannerRef}
                      customTemplate={activePublishedTemplate}
                      fields={currentCatDef?.fields || []}
                    />
                  </div>
                </div>

                {/* Optional Side-by-Side Reference Specimen View */}
                {showSpecimenCompare && specimensForCat.length > 0 && (
                  <div
                    style={{
                      display: 'flex',
                      flexDirection: 'column',
                      alignItems: 'center',
                      maxWidth: 640,
                    }}
                  >
                    <div
                      style={{
                        marginBottom: 8,
                        display: 'flex',
                        alignItems: 'center',
                        gap: 8,
                        background: '#FFFFFF',
                        padding: '4px 12px',
                        borderRadius: 20,
                        boxShadow: '0 1px 3px rgba(0,0,0,0.08)',
                      }}
                    >
                      <span style={{ fontSize: 12, fontWeight: 800, color: '#6D28D9' }}>
                        📌 受領標本デザイン比較:
                      </span>
                      {specimensForCat.map((sp, idx) => (
                        <button
                          key={idx}
                          onClick={() => setSpecimenIndex(idx)}
                          style={{
                            background: specimenIndex === idx ? '#6D28D9' : '#F3F4F6',
                            color: specimenIndex === idx ? '#FFFFFF' : '#374151',
                            border: 'none',
                            borderRadius: 12,
                            padding: '2px 8px',
                            fontSize: 11,
                            fontWeight: 700,
                            cursor: 'pointer',
                          }}
                        >
                          {sp.label}
                        </button>
                      ))}
                    </div>
                    <img
                      src={specimensForCat[specimenIndex]?.src}
                      alt="標本デザイン"
                      style={{
                        maxWidth: '100%',
                        borderRadius: 4,
                        boxShadow: '0 10px 25px rgba(0,0,0,0.18)',
                        border: '2px solid #7C3AED',
                      }}
                    />
                  </div>
                )}
              </div>
            ) : (
              <div style={{ padding: 40, color: '#64748B', fontWeight: 700 }}>
                左側のリストから商品を選択してください。
              </div>
            )}
          </div>
        </main>

        {/* RIGHT PANE: Interactive Spec Editor & Master Info */}
        <aside
          style={{
            background: '#FFFFFF',
            borderLeft: '1px solid #CBD5E1',
            display: 'flex',
            flexDirection: 'column',
            height: 'calc(100vh - 108px)',
          }}
        >
          {/* Tabs */}
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: '1fr 1fr 0.8fr',
              borderBottom: '1px solid #CBD5E1',
              background: '#F8FAFC',
            }}
          >
            <button
              onClick={() => setRightTab('specs')}
              style={{
                padding: '11px 6px',
                border: 'none',
                borderBottom: rightTab === 'specs' ? '3px solid #003E92' : '3px solid transparent',
                background: rightTab === 'specs' ? '#FFFFFF' : 'transparent',
                color: rightTab === 'specs' ? '#003E92' : '#64748B',
                fontWeight: 900,
                fontSize: 12.5,
                cursor: 'pointer',
              }}
            >
              ✏️ 機能表スペック編集
            </button>
            <button
              onClick={() => setRightTab('master')}
              style={{
                padding: '11px 6px',
                border: 'none',
                borderBottom: rightTab === 'master' ? '3px solid #003E92' : '3px solid transparent',
                background: rightTab === 'master' ? '#FFFFFF' : 'transparent',
                color: rightTab === 'master' ? '#003E92' : '#64748B',
                fontWeight: 900,
                fontSize: 12.5,
                cursor: 'pointer',
              }}
            >
              📦 商品マスタ情報
            </button>
            <button
              onClick={() => setRightTab('mail_logs')}
              style={{
                padding: '11px 6px',
                border: 'none',
                borderBottom:
                  rightTab === 'mail_logs' ? '3px solid #003E92' : '3px solid transparent',
                background: rightTab === 'mail_logs' ? '#FFFFFF' : 'transparent',
                color: rightTab === 'mail_logs' ? '#003E92' : '#64748B',
                fontWeight: 900,
                fontSize: 12.5,
                cursor: 'pointer',
              }}
            >
              📨 送信履歴 ({emailLogs.length})
            </button>
          </div>

          {/* Tab 1: Interactive Spec Editor */}
          {rightTab === 'specs' && selectedProduct && (
            <>
              <div
                style={{
                  padding: '10px 14px',
                  borderBottom: '1px solid #E2E8F0',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  background: '#F8FAFC',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, minWidth: 0, flex: 1 }}>
                  <span style={{ fontSize: 11.5, fontWeight: 800, whiteSpace: 'nowrap' }}>
                    テンプレート:
                  </span>
                  <select
                    value={activeTemplateVariant === 'auto' ? `cat:${liveCategory}` : `tpl:${activeTemplateVariant}`}
                    onChange={(e) => {
                      const val = e.target.value;
                      if (val.startsWith('cat:')) {
                        const nextCat = val.replace('cat:', '') as CategoryId;
                        setLiveCategory(nextCat);
                        setActiveTemplateVariant('auto');
                      } else if (val.startsWith('tpl:')) {
                        const tid = val.replace('tpl:', '');
                        const found = publishedTemplates.find((t) => t.template_id === tid);
                        if (found) {
                          setLiveCategory(found.category);
                          setActiveTemplateVariant(found.template_id);
                          if (found.custom_fields) {
                            setLiveSpecs((prev) => {
                              const next = { ...prev };
                              for (const cf of found.custom_fields || []) {
                                if (next[cf.key] === undefined && cf.default !== undefined) {
                                  next[cf.key] = cf.default;
                                }
                              }
                              return next;
                            });
                          }
                        }
                      }
                    }}
                    style={{
                      padding: '4px 8px',
                      borderRadius: 5,
                      border: '1px solid #CBD5E1',
                      fontSize: 11.5,
                      fontWeight: 800,
                      maxWidth: 215,
                    }}
                  >
                    <optgroup label="⭐ 標準カテゴリテンプレート">
                      {categories.map((c) => (
                        <option key={c.id} value={`cat:${c.id}`}>
                          標準: {c.name} ({c.en_name})
                        </option>
                      ))}
                    </optgroup>
                    {publishedTemplates.length > 0 && (
                      <optgroup label="🚀 公開カスタムテンプレート（デザイナー作成）">
                        {publishedTemplates.map((pt) => (
                          <option key={pt.template_id} value={`tpl:${pt.template_id}`}>
                            🚀 {pt.name}
                          </option>
                        ))}
                      </optgroup>
                    )}
                  </select>
                </div>

                <button
                  onClick={handleSaveSpecs}
                  disabled={saving}
                  style={{
                    background: '#003E92',
                    color: '#FFFFFF',
                    border: 'none',
                    borderRadius: 6,
                    padding: '6px 12px',
                    fontSize: 12,
                    fontWeight: 800,
                    cursor: 'pointer',
                  }}
                >
                  {saving ? '保存中...' : '☁️ バナー保存 (GCS/BQ)'}
                </button>
              </div>

              <div style={{ flex: 1, overflowY: 'auto', padding: 14 }}>
                {Object.entries(groupedFields).map(([groupName, fields]) => (
                  <div
                    key={groupName}
                    style={{
                      marginBottom: 16,
                      border: '1px solid #E2E8F0',
                      borderRadius: 8,
                      overflow: 'hidden',
                    }}
                  >
                    <div
                      style={{
                        background: '#F1F5F9',
                        padding: '6px 12px',
                        fontWeight: 900,
                        fontSize: 12,
                        color: '#1E293B',
                        borderBottom: '1px solid #E2E8F0',
                      }}
                    >
                      ■ {groupName}
                    </div>
                    <div
                      style={{
                        padding: 10,
                        display: 'grid',
                        gridTemplateColumns: '1fr 1fr',
                        gap: 8,
                      }}
                    >
                      {fields.map((f) => {
                        const val = liveSpecs[f.key] ?? '';
                        const isDoorLayout = f.key === 'door_layout';
                        const isWide =
                          isDoorLayout ||
                          f.key.includes('office') ||
                          f.key.includes('feature') ||
                          f.key.includes('point') ||
                          f.key.includes('recording') ||
                          f.key.includes('cpu_series');
                        return (
                          <div
                            key={f.key}
                            style={{
                              gridColumn: isWide ? '1 / -1' : 'auto',
                              display: 'flex',
                              flexDirection: 'column',
                              gap: 4,
                            }}
                          >
                            <label
                              style={{
                                fontSize: 11,
                                fontWeight: 700,
                                color: '#475569',
                              }}
                            >
                              {f.label}
                              {f.unit ? ` (${f.unit})` : ''}
                            </label>
                            {f.choices && f.choices.length > 0 ? (
                              <>
                                <select
                                  value={String(val)}
                                  onChange={(e) => {
                                    const nextVal = e.target.value;
                                    if (isDoorLayout) {
                                      applyDoorLayoutChange(nextVal);
                                    } else {
                                      setLiveSpecs((prev) => ({
                                        ...prev,
                                        [f.key]: nextVal,
                                      }));
                                    }
                                  }}
                                  style={{
                                    padding: '5px 7px',
                                    borderRadius: 5,
                                    border: '1px solid #CBD5E1',
                                    fontSize: 12,
                                    fontWeight: 700,
                                  }}
                                >
                                  {f.choices.map((ch) => (
                                    <option key={ch} value={ch}>
                                      {ch}
                                      {isDoorLayout && DOOR_LAYOUT_PRESETS[ch]
                                        ? ` — ${DOOR_LAYOUT_PRESETS[ch].description}`
                                        : ''}
                                    </option>
                                  ))}
                                </select>

                                {/* Visual 12-Layout Selector Grid for 3D Door Layouts */}
                                {isDoorLayout && (
                                  <div
                                    style={{
                                      marginTop: 4,
                                      background: '#F8FAFC',
                                      border: '1px solid #E2E8F0',
                                      borderRadius: 6,
                                      padding: 8,
                                    }}
                                  >
                                    <div
                                      style={{
                                        fontSize: 10.5,
                                        fontWeight: 800,
                                        color: '#1E40AF',
                                        marginBottom: 6,
                                      }}
                                    >
                                      📐 3Dレイアウト選択ガイド（クリックで即時切替・各室構造連動）:
                                    </div>
                                    <div
                                      style={{
                                        display: 'grid',
                                        gridTemplateColumns: 'repeat(4, 1fr)',
                                        gap: 5,
                                      }}
                                    >
                                      {f.choices.map((ch) => {
                                        const selected = String(val || '扉1枚B') === ch;
                                        return (
                                          <button
                                            key={ch}
                                            type="button"
                                            onClick={() => applyDoorLayoutChange(ch)}
                                            style={{
                                              border: selected
                                                ? '2px solid #0055B8'
                                                : '1px solid #CBD5E1',
                                              background: selected ? '#EFF6FF' : '#FFFFFF',
                                              borderRadius: 5,
                                              padding: '4px 3px',
                                              cursor: 'pointer',
                                              display: 'flex',
                                              flexDirection: 'column',
                                              alignItems: 'center',
                                              gap: 2,
                                            }}
                                          >
                                            <img
                                              src={DOOR_IMAGE_MAP[ch] || '/assets/doors/door_1b.png'}
                                              alt={ch}
                                              style={{
                                                height: 36,
                                                width: 'auto',
                                                objectFit: 'contain',
                                                display: 'block',
                                              }}
                                            />
                                            <span
                                              style={{
                                                fontSize: 10,
                                                fontWeight: selected ? 900 : 700,
                                                color: selected ? '#003E92' : '#334155',
                                                whiteSpace: 'nowrap',
                                              }}
                                            >
                                              {ch}
                                            </span>
                                          </button>
                                        );
                                      })}
                                    </div>
                                  </div>
                                )}
                              </>
                            ) : (
                              <input
                                type={f.type === 'number' ? 'number' : 'text'}
                                value={String(val)}
                                onChange={(e) =>
                                  setLiveSpecs((prev) => ({
                                    ...prev,
                                    [f.key]:
                                      f.type === 'number'
                                        ? e.target.value === ''
                                          ? ''
                                          : Number(e.target.value)
                                        : e.target.value,
                                  }))
                                }
                                style={{
                                  padding: '5px 8px',
                                  borderRadius: 5,
                                  border: '1px solid #CBD5E1',
                                  fontSize: 12,
                                }}
                              />
                            )}
                          </div>
                        );
                      })}
                    </div>
                  </div>
                ))}
              </div>
            </>
          )}

          {/* Tab 2: Linked Master Info */}
          {rightTab === 'master' && selectedProduct && (
            <div style={{ flex: 1, overflowY: 'auto', padding: 16 }}>
              <div
                style={{
                  background: '#EFF6FF',
                  border: '1px solid #BFDBFE',
                  borderRadius: 8,
                  padding: 12,
                  marginBottom: 14,
                }}
              >
                <div style={{ fontSize: 12, fontWeight: 900, color: '#1E40AF' }}>
                  🔒 商品マスタ参照（読み取り専用 Read-Only）
                </div>
                <div style={{ fontSize: 11.5, color: '#1E3A8A', marginTop: 4, lineHeight: 1.45 }}>
                  商品マスタ (`mst_product`) は読み取り専用で保護されています。本ツールでのバナー保存は専用ストレージ（GCS / BigQuery）にのみ保存されます。
                </div>
              </div>

              <table
                style={{
                  width: '100%',
                  borderCollapse: 'collapse',
                  fontSize: 12.5,
                }}
              >
                <tbody>
                  {[
                    ['マスタID', selectedProduct.product_id || '-'],
                    ['JANコード', selectedProduct.jan_code],
                    ['検索型番 / 店舗型番', selectedProduct.search_model_no],
                    ['メーカーコード', selectedProduct.maker_code || '-'],
                    ['メーカー名', selectedProduct.maker_name],
                    ['商品名', selectedProduct.product_name],
                    ['クラスコード', selectedProduct.class_code || '-'],
                    [
                      'Cymbal 売価 (税込)',
                      `¥${(selectedProduct.edion_price || 0).toLocaleString()}`,
                    ],
                    [
                      '仕切原価',
                      `¥${(selectedProduct.shikiri_price || 0).toLocaleString()}`,
                    ],
                    ['粗利率', `${selectedProduct.margin_rate}%`],
                    ['メーカー希望小売価格', selectedProduct.maker_price],
                    ['長期保証区分', `${selectedProduct.long_warranty}ヶ月`],
                    ['効力開始日', selectedProduct.effective_date || '2026-12-01'],
                    ['商品特長', selectedProduct.features || '-'],
                    [
                      '店頭POPコメント',
                      [
                        selectedProduct.rec_comment_1,
                        selectedProduct.rec_comment_2,
                        selectedProduct.rec_comment_3,
                      ]
                        .filter(Boolean)
                        .join(' / ') || '-',
                    ],
                  ].map(([k, v]) => (
                    <tr key={String(k)} style={{ borderBottom: '1px solid #E2E8F0' }}>
                      <th
                        style={{
                          textAlign: 'left',
                          padding: '8px 6px',
                          color: '#475569',
                          width: '42%',
                          fontWeight: 700,
                        }}
                      >
                        {k}
                      </th>
                      <td style={{ padding: '8px 6px', fontWeight: 800, color: '#0F172A' }}>
                        {v}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>

              {selectedProduct.ai_metadata?.summary && (
                <div
                  style={{
                    marginTop: 16,
                    background: '#F5F3FF',
                    border: '1px solid #DDD6FE',
                    borderRadius: 8,
                    padding: 12,
                  }}
                >
                  <div style={{ fontSize: 12, fontWeight: 900, color: '#5B21B6' }}>
                    ✨ Gemini 2.5 Flash グラウンディング履歴
                  </div>
                  <div style={{ fontSize: 11.5, marginTop: 4, lineHeight: 1.4 }}>
                    {selectedProduct.ai_metadata.summary}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Tab 3: Email Logs */}
          {rightTab === 'mail_logs' && (
            <div style={{ flex: 1, overflowY: 'auto', padding: 12 }}>
              {emailLogs.length === 0 ? (
                <div style={{ color: '#64748B', fontSize: 12.5, padding: 20, textAlign: 'center' }}>
                  まだメール送信履歴はありません。
                </div>
              ) : (
                emailLogs.map((log) => (
                  <div
                    key={log.id}
                    style={{
                      border: '1px solid #E2E8F0',
                      borderRadius: 8,
                      padding: 10,
                      marginBottom: 8,
                      fontSize: 12,
                    }}
                  >
                    <div
                      style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        marginBottom: 4,
                      }}
                    >
                      <span
                        style={{
                          background: '#DCFCE7',
                          color: '#166534',
                          fontWeight: 800,
                          fontSize: 10.5,
                          padding: '1px 6px',
                          borderRadius: 4,
                        }}
                      >
                        {log.status} ({log.delivery_method})
                      </span>
                      <span style={{ fontSize: 10.5, color: '#64748B' }}>
                        {log.created_at ? new Date(log.created_at).toLocaleString('ja-JP') : ''}
                      </span>
                    </div>
                    <div style={{ fontWeight: 800 }}>{log.subject}</div>
                    <div style={{ color: '#475569', fontSize: 11.5 }}>宛先: {log.to_email}</div>
                    <div
                      style={{
                        display: 'flex',
                        gap: 8,
                        marginTop: 6,
                        fontSize: 11,
                      }}
                    >
                      {log.meta?.jpg_download_url && (
                        <a
                          href={log.meta.jpg_download_url}
                          target="_blank"
                          rel="noreferrer"
                          style={{ color: '#0284C7', fontWeight: 700 }}
                        >
                          🖼️ 添付JPEGを表示
                        </a>
                      )}
                      {log.meta?.pdf_download_url && (
                        <a
                          href={log.meta.pdf_download_url}
                          target="_blank"
                          rel="noreferrer"
                          style={{ color: '#059669', fontWeight: 700 }}
                        >
                          📄 添付PDFを表示
                        </a>
                      )}
                    </div>
                  </div>
                ))
              )}
            </div>
          )}
        </aside>
      </div>
      </>
      )}

      {/* EMAIL ATTACHMENT MODAL */}
      {showEmailModal && selectedProduct && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(15, 23, 42, 0.55)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 50,
          }}
        >
          <div
            style={{
              background: '#FFFFFF',
              borderRadius: 12,
              width: 540,
              maxWidth: '94vw',
              padding: 24,
              boxShadow: '0 20px 45px rgba(0,0,0,0.25)',
            }}
          >
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                marginBottom: 14,
              }}
            >
              <h3 style={{ margin: 0, fontSize: 18, fontWeight: 900, color: '#003E92' }}>
                ✉️ 機能表バナーをメールに添付して送信
              </h3>
              <button
                onClick={() => setShowEmailModal(false)}
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

            <form onSubmit={handleSendEmail} style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              <div>
                <label style={{ fontSize: 12, fontWeight: 800, display: 'block', marginBottom: 4 }}>
                  送信先メールアドレス (To) *
                </label>
                <input
                  type="email"
                  required
                  value={emailTo}
                  onChange={(e) => setEmailTo(e.target.value)}
                  style={{
                    width: '100%',
                    padding: '8px 10px',
                    borderRadius: 6,
                    border: '1px solid #CBD5E1',
                    fontSize: 13,
                    boxSizing: 'border-box',
                  }}
                />
              </div>

              <div>
                <label style={{ fontSize: 12, fontWeight: 800, display: 'block', marginBottom: 4 }}>
                  CC メールアドレス (任意)
                </label>
                <input
                  type="text"
                  value={emailCc}
                  onChange={(e) => setEmailCc(e.target.value)}
                  placeholder="md-team@cymbal-retail.example.com"
                  style={{
                    width: '100%',
                    padding: '8px 10px',
                    borderRadius: 6,
                    border: '1px solid #CBD5E1',
                    fontSize: 13,
                    boxSizing: 'border-box',
                  }}
                />
              </div>

              <div>
                <label style={{ fontSize: 12, fontWeight: 800, display: 'block', marginBottom: 4 }}>
                  添付ファイル形式
                </label>
                <div style={{ display: 'flex', gap: 10 }}>
                  {[
                    { id: 'both', label: '両方添付 (JPEG + PDF) 推奨' },
                    { id: 'jpeg', label: 'JPEGのみ (.jpg)' },
                    { id: 'pdf', label: 'PDFのみ (.pdf)' },
                  ].map((opt) => (
                    <label
                      key={opt.id}
                      style={{
                        flex: 1,
                        border:
                          emailFormat === opt.id ? '2px solid #003E92' : '1px solid #CBD5E1',
                        background: emailFormat === opt.id ? '#EFF6FF' : '#FFFFFF',
                        borderRadius: 6,
                        padding: '8px 8px',
                        fontSize: 12,
                        fontWeight: 800,
                        cursor: 'pointer',
                        textAlign: 'center',
                      }}
                    >
                      <input
                        type="radio"
                        name="attachment_format"
                        value={opt.id}
                        checked={emailFormat === opt.id}
                        onChange={() => setEmailFormat(opt.id as any)}
                        style={{ marginRight: 5 }}
                      />
                      {opt.label}
                    </label>
                  ))}
                </div>
              </div>

              <div>
                <label style={{ fontSize: 12, fontWeight: 800, display: 'block', marginBottom: 4 }}>
                  件名 (Subject)
                </label>
                <input
                  type="text"
                  required
                  value={emailSubject}
                  onChange={(e) => setEmailSubject(e.target.value)}
                  style={{
                    width: '100%',
                    padding: '8px 10px',
                    borderRadius: 6,
                    border: '1px solid #CBD5E1',
                    fontSize: 13,
                    boxSizing: 'border-box',
                  }}
                />
              </div>

              <div>
                <label style={{ fontSize: 12, fontWeight: 800, display: 'block', marginBottom: 4 }}>
                  本文 (Body)
                </label>
                <textarea
                  rows={5}
                  value={emailBody}
                  onChange={(e) => setEmailBody(e.target.value)}
                  style={{
                    width: '100%',
                    padding: '8px 10px',
                    borderRadius: 6,
                    border: '1px solid #CBD5E1',
                    fontSize: 12.5,
                    boxSizing: 'border-box',
                    fontFamily: 'inherit',
                  }}
                />
              </div>

              {lastSentResult && (
                <div
                  style={{
                    background: '#DCFCE7',
                    border: '1px solid #86EFAC',
                    borderRadius: 8,
                    padding: 12,
                    fontSize: 12,
                    color: '#14532D',
                  }}
                >
                  <div style={{ fontWeight: 900, marginBottom: 4 }}>
                    ✅ メール送信完了 (ステータス: {lastSentResult.status} / 方式:{' '}
                    {lastSentResult.delivery_method})
                  </div>
                  <div style={{ display: 'flex', gap: 12, marginTop: 6 }}>
                    <a
                      href={lastSentResult.jpeg_download_url}
                      target="_blank"
                      rel="noreferrer"
                      style={{ color: '#0369A1', fontWeight: 800 }}
                    >
                      🖼️ 生成されたJPEGを確認 ({Math.round(lastSentResult.jpeg_size_bytes / 1024)}KB)
                    </a>
                    <a
                      href={lastSentResult.pdf_download_url}
                      target="_blank"
                      rel="noreferrer"
                      style={{ color: '#047857', fontWeight: 800 }}
                    >
                      📄 生成されたPDFを確認 ({Math.round(lastSentResult.pdf_size_bytes / 1024)}KB)
                    </a>
                  </div>
                </div>
              )}

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 6 }}>
                <button
                  type="button"
                  onClick={() => setShowEmailModal(false)}
                  style={{
                    background: '#F1F5F9',
                    color: '#334155',
                    border: '1px solid #CBD5E1',
                    borderRadius: 6,
                    padding: '8px 16px',
                    fontSize: 13,
                    fontWeight: 700,
                    cursor: 'pointer',
                  }}
                >
                  閉じる
                </button>
                <button
                  type="submit"
                  disabled={sendingEmail}
                  style={{
                    background: '#EA5514',
                    color: '#FFFFFF',
                    border: 'none',
                    borderRadius: 6,
                    padding: '8px 20px',
                    fontSize: 13,
                    fontWeight: 900,
                    cursor: 'pointer',
                  }}
                >
                  {sendingEmail ? '添付ファイルを生成・送信中...' : '📨 今すぐ送信する'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* NEW PRODUCT MODAL */}
      {showNewModal && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(15, 23, 42, 0.55)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 50,
          }}
        >
          <div
            style={{
              background: '#FFFFFF',
              borderRadius: 12,
              width: 460,
              maxWidth: '94vw',
              padding: 24,
              boxShadow: '0 20px 45px rgba(0,0,0,0.25)',
            }}
          >
            <h3 style={{ margin: '0 0 14px', fontSize: 17, fontWeight: 900, color: '#003E92' }}>
              ＋ 新規商品・機能表の登録（商品マスタ同時登録）
            </h3>
            <form onSubmit={handleCreateProduct} style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              <div>
                <label style={{ fontSize: 12, fontWeight: 800 }}>カテゴリ</label>
                <select
                  value={newCat}
                  onChange={(e) => setNewCat(e.target.value as CategoryId)}
                  style={{
                    width: '100%',
                    padding: '7px 10px',
                    borderRadius: 6,
                    border: '1px solid #CBD5E1',
                    marginTop: 3,
                  }}
                >
                  {categories.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name} ({c.en_name})
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label style={{ fontSize: 12, fontWeight: 800 }}>JANコード *</label>
                <input
                  type="text"
                  required
                  placeholder="4548736167999"
                  value={newJan}
                  onChange={(e) => setNewJan(e.target.value)}
                  style={{
                    width: '100%',
                    padding: '7px 10px',
                    borderRadius: 6,
                    border: '1px solid #CBD5E1',
                    marginTop: 3,
                    boxSizing: 'border-box',
                  }}
                />
              </div>
              <div>
                <label style={{ fontSize: 12, fontWeight: 800 }}>型番 *</label>
                <input
                  type="text"
                  required
                  placeholder="K65XR90"
                  value={newModel}
                  onChange={(e) => setNewModel(e.target.value)}
                  style={{
                    width: '100%',
                    padding: '7px 10px',
                    borderRadius: 6,
                    border: '1px solid #CBD5E1',
                    marginTop: 3,
                    boxSizing: 'border-box',
                  }}
                />
              </div>
              <div>
                <label style={{ fontSize: 12, fontWeight: 800 }}>メーカー名</label>
                <input
                  type="text"
                  placeholder="SONY"
                  value={newMaker}
                  onChange={(e) => setNewMaker(e.target.value)}
                  style={{
                    width: '100%',
                    padding: '7px 10px',
                    borderRadius: 6,
                    border: '1px solid #CBD5E1',
                    marginTop: 3,
                    boxSizing: 'border-box',
                  }}
                />
              </div>
              <div>
                <label style={{ fontSize: 12, fontWeight: 800 }}>商品名</label>
                <input
                  type="text"
                  placeholder="4K Mini LED液晶テレビ 65V型"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  style={{
                    width: '100%',
                    padding: '7px 10px',
                    borderRadius: 6,
                    border: '1px solid #CBD5E1',
                    marginTop: 3,
                    boxSizing: 'border-box',
                  }}
                />
              </div>
              <div>
                <label style={{ fontSize: 12, fontWeight: 800 }}>Cymbal 売価 (税込・円)</label>
                <input
                  type="number"
                  value={newPrice}
                  onChange={(e) => setNewPrice(e.target.value)}
                  style={{
                    width: '100%',
                    padding: '7px 10px',
                    borderRadius: 6,
                    border: '1px solid #CBD5E1',
                    marginTop: 3,
                    boxSizing: 'border-box',
                  }}
                />
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 10 }}>
                <button
                  type="button"
                  onClick={() => setShowNewModal(false)}
                  style={{
                    background: '#F1F5F9',
                    border: '1px solid #CBD5E1',
                    borderRadius: 6,
                    padding: '7px 14px',
                    cursor: 'pointer',
                  }}
                >
                  キャンセル
                </button>
                <button
                  type="submit"
                  disabled={saving}
                  style={{
                    background: '#003E92',
                    color: '#FFFFFF',
                    border: 'none',
                    borderRadius: 6,
                    padding: '7px 16px',
                    fontWeight: 800,
                    cursor: 'pointer',
                  }}
                >
                  登録する
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
