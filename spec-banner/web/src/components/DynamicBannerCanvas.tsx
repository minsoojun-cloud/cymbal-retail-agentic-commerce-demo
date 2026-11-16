import React, { useRef } from 'react';
import { CategoryField, LayoutBox, TemplateSchema } from '../types';
import { DoorDiagram3DWithDimensions } from './templates/DoorDiagram3D';
import {
  DoorSwingDiagramSvg,
  EAngleSelectPanel,
  JanBarcodeSvg,
  RecyclingFooterBar,
  StarRatingRow,
  UnifiedEnergyLabelBox,
} from './templates/SharedBannerParts';

const VOD_DEFS = [
  { key: 'vod_netflix', label: 'NETFLIX', color: '#E50914' },
  { key: 'vod_youtube', label: 'YouTube', color: '#FF0000' },
  { key: 'vod_unext', label: 'U-NEXT', color: '#005BAC' },
  { key: 'vod_tver', label: 'TVer', color: '#0095D9' },
  { key: 'vod_prime', label: 'Prime Video', color: '#0073BB' },
  { key: 'vod_abema', label: 'ABEMA', color: '#111111' },
  { key: 'vod_disney', label: 'Disney+', color: '#113CCF' },
  { key: 'vod_dazn', label: 'DAZN', color: '#111111' },
  { key: 'vod_hulu', label: 'hulu', color: '#00A850' },
  { key: 'vod_lemino', label: 'Lemino', color: '#E60033' },
];

function computeAutoFontSize(
  text: string,
  boxW: number,
  boxH: number,
  isHero: boolean,
  unitLen: number = 0
): number {
  const effectiveChars = Math.max(1, text.length + unitLen * 0.65);
  const availW = Math.max(36, boxW - 18);
  const availH = Math.max(24, boxH - 34);
  const baseByHeight = isHero ? availH * 0.48 : availH * 0.38;
  const maxByWidth = (availW / effectiveChars) * (isHero ? 1.32 : 1.08);
  return Math.max(
    8.5,
    Math.min(isHero ? 96 : 32, Math.round(Math.min(baseByHeight, maxByWidth) * 10) / 10)
  );
}

export interface DynamicBannerCanvasProps {
  template: TemplateSchema;
  specs: Record<string, any>;
  fields: CategoryField[];
  canvasRef: React.RefObject<HTMLDivElement>;
  selectedBoxId: string | null;
  selectedHeaderSlot: string | null;
  highlightedFieldKey: string | null;
  showGrid: boolean;
  overlayOpacity: number;
  interactive: boolean;
  onSelectBox: (boxId: string | null) => void;
  onSelectHeaderSlot: (slotKey: string | null) => void;
  onUpdateBox: (boxId: string, patch: Partial<LayoutBox>) => void;
  onBindFieldToBox: (boxId: string, fieldKey: string, fieldLabel?: string) => void;
  onBindFieldToHeaderSlot: (slotName: string, fieldKey: string) => void;
}

export const DynamicBannerCanvas: React.FC<DynamicBannerCanvasProps> = ({
  template,
  specs,
  fields,
  canvasRef,
  selectedBoxId,
  selectedHeaderSlot,
  highlightedFieldKey,
  showGrid,
  overlayOpacity,
  interactive,
  onSelectBox,
  onSelectHeaderSlot,
  onUpdateBox,
  onBindFieldToBox,
  onBindFieldToHeaderSlot,
}) => {
  const dragStateRef = useRef<{
    boxId: string;
    mode: 'move' | 'resize';
    startX: number;
    startY: number;
    origX: number;
    origY: number;
    origW: number;
    origH: number;
  } | null>(null);

  const fieldByKey = React.useMemo(() => {
    const map: Record<string, CategoryField> = {};
    for (const f of fields) map[f.key] = f;
    for (const cf of template.custom_fields || []) map[cf.key] = cf;
    return map;
  }, [fields, template.custom_fields]);

  const snap = (v: number) => {
    const g = template.grid_snap_px || 4;
    return Math.round(v / g) * g;
  };

  const startBoxMouseAction = (
    e: React.MouseEvent,
    box: LayoutBox,
    mode: 'move' | 'resize'
  ) => {
    if (!interactive) return;
    e.stopPropagation();
    onSelectBox(box.id);
    onSelectHeaderSlot(null);

    dragStateRef.current = {
      boxId: box.id,
      mode,
      startX: e.clientX,
      startY: e.clientY,
      origX: box.x,
      origY: box.y,
      origW: box.w,
      origH: box.h,
    };

    const handleMouseMove = (ev: MouseEvent) => {
      const st = dragStateRef.current;
      if (!st) return;
      const dx = ev.clientX - st.startX;
      const dy = ev.clientY - st.startY;
      if (st.mode === 'move') {
        const nx = Math.max(0, Math.min(template.canvas_width - st.origW, snap(st.origX + dx)));
        const ny = Math.max(0, Math.min(template.canvas_height - st.origH, snap(st.origY + dy)));
        onUpdateBox(st.boxId, { x: nx, y: ny });
      } else {
        const nw = Math.max(48, Math.min(template.canvas_width - st.origX, snap(st.origW + dx)));
        const nh = Math.max(36, Math.min(template.canvas_height - st.origY, snap(st.origH + dy)));
        onUpdateBox(st.boxId, { w: nw, h: nh });
      }
    };

    const handleMouseUp = () => {
      dragStateRef.current = null;
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
    };

    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);
  };

  const resolveHeaderMainTitle = () => {
    const h = template.header;
    if (h.main_title_mode === 'field' && h.main_title_field_key) {
      const raw = String(specs[h.main_title_field_key] ?? '');
      if (template.category === 'tv') {
        if (raw === 'MiniLED') return 'Mini LED テレビ';
        if (raw === '有機EL') return '有機ELテレビ';
        if (raw === '2K液晶') return '2K液晶テレビ';
        if (raw === '4K液晶') return '4K液晶テレビ';
      }
      if (template.category === 'refrigerator' && h.main_title_field_key === 'capacity_l') {
        return `定格内容量 ${raw || '595'}L 冷蔵庫`;
      }
      if (raw) return raw;
    }
    return h.main_title_static || '機能表タイトル';
  };

  const renderBoxBody = (box: LayoutBox) => {
    const fk = box.binding.field_key;
    const rawVal = specs[fk] ?? box.binding.empty_fallback ?? '-';
    const valStr = String(rawVal);
    const fDef = fieldByKey[fk];
    const unitStr =
      box.binding.unit_override !== undefined && box.binding.unit_override !== null
        ? box.binding.unit_override
        : fDef?.unit || '';
    const prefixStr = box.binding.prefix_text || '';

    if (box.box_type === 'header_banner') {
      const subKeys = box.binding.sub_field_keys || ['maker', 'brand', 'model_no'];
      const topRight1Key = subKeys[0] || '';
      const topRight2Key = subKeys[1] || '';
      const bottomRightKey = subKeys[2] || '';

      const topRight1 = topRight1Key ? String(specs[topRight1Key] ?? '') : '';
      const topRight2 = topRight2Key ? String(specs[topRight2Key] ?? '') : '';
      const bottomRight = bottomRightKey ? String(specs[bottomRightKey] ?? '') : '';

      let mainHeadline = box.title || valStr;
      if (fk && specs[fk]) {
        const raw = String(specs[fk]);
        if (template.category === 'tv') {
          if (raw === 'MiniLED') mainHeadline = 'Mini LED テレビ';
          else if (raw === '有機EL') mainHeadline = '有機ELテレビ';
          else if (raw === '2K液晶') mainHeadline = '2K液晶テレビ';
          else if (raw === '4K液晶') mainHeadline = '4K液晶テレビ';
          else mainHeadline = raw;
        } else if (template.category === 'refrigerator' && fk === 'capacity_l') {
          mainHeadline = `定格内容量 ${raw}L 冷蔵庫`;
        } else {
          mainHeadline = raw;
        }
      }

      const updateSubSlot = (slotIdx: number, newFieldKey: string) => {
        const nextSub = [...(box.binding.sub_field_keys || ['maker', 'brand', 'model_no'])];
        while (nextSub.length < 3) nextSub.push('');
        nextSub[slotIdx] = newFieldKey;
        onUpdateBox(box.id, {
          binding: {
            ...box.binding,
            sub_field_keys: nextSub,
          },
        });
      };

      const renderSubBadge = (slotIdx: number, fieldKey: string, slotLabel: string) => {
        if (!interactive) return null;
        const isHigh = highlightedFieldKey && highlightedFieldKey === fieldKey;
        return (
          <span
            data-export-ignore="true"
            style={{
              display: 'inline-block',
              marginLeft: 4,
              padding: '1px 5px',
              fontSize: 9,
              fontWeight: 800,
              borderRadius: 4,
              background: isHigh ? '#DC2626' : 'rgba(0,0,0,0.45)',
              color: '#FFFFFF',
              border: isHigh ? '1.5px solid #FEF08A' : '1px solid rgba(255,255,255,0.45)',
            }}
            title={`${slotLabel}: 右ペインの項目をここへドラッグ＆ドロップして変更可`}
          >
            🎯 {fieldByKey[fieldKey]?.label || fieldKey || '未割当'}
          </span>
        );
      };

      return (
        <div
          style={{
            flex: 1,
            background: box.bg_color || '#1B9E3E',
            color: box.value_color || '#FFFFFF',
            padding: '10px 20px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            overflow: 'hidden',
          }}
        >
          {/* Left Headline Slot */}
          <div
            onDragOver={(e) => {
              e.preventDefault();
              e.stopPropagation();
            }}
            onDrop={(e) => {
              e.preventDefault();
              e.stopPropagation();
              const droppedKey = e.dataTransfer.getData('text/field_key');
              const droppedLabel = e.dataTransfer.getData('text/field_label');
              if (droppedKey) {
                onBindFieldToBox(box.id, droppedKey, droppedLabel || box.title);
              }
            }}
            style={{
              fontSize: Math.min(40, Math.max(18, Math.round(box.h * 0.45))),
              fontWeight: 900,
              lineHeight: 1.05,
              whiteSpace: 'nowrap',
            }}
          >
            {mainHeadline}
            {interactive && (
              <span
                data-export-ignore="true"
                style={{
                  display: 'inline-block',
                  marginLeft: 6,
                  padding: '1px 5px',
                  fontSize: 9,
                  fontWeight: 800,
                  borderRadius: 4,
                  background:
                    highlightedFieldKey === fk ? '#DC2626' : 'rgba(0,0,0,0.45)',
                  color: '#FFFFFF',
                  border: '1px solid rgba(255,255,255,0.45)',
                  verticalAlign: 'middle',
                }}
              >
                🎯 {fieldByKey[fk]?.label || fk || '固定タイトル'}
              </span>
            )}
          </div>

          {/* Right 3 Sub-slots: Top-Right 1 (Maker), Top-Right 2 (Brand), Bottom-Right (Model No) */}
          <div style={{ textAlign: 'left', whiteSpace: 'nowrap' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <div
                onDragOver={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                }}
                onDrop={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  const droppedKey = e.dataTransfer.getData('text/field_key');
                  if (droppedKey) updateSubSlot(0, droppedKey);
                }}
                style={{ fontSize: 15, fontWeight: 800 }}
              >
                {topRight1}
                {renderSubBadge(0, topRight1Key, 'ヘッダー右上①')}
              </div>

              <div
                onDragOver={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                }}
                onDrop={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  const droppedKey = e.dataTransfer.getData('text/field_key');
                  if (droppedKey) updateSubSlot(1, droppedKey);
                }}
                style={{ fontSize: 15, fontWeight: 800 }}
              >
                {topRight2}
                {renderSubBadge(1, topRight2Key, 'ヘッダー右上②')}
              </div>
            </div>

            <div
              onDragOver={(e) => {
                e.preventDefault();
                e.stopPropagation();
              }}
              onDrop={(e) => {
                e.preventDefault();
                e.stopPropagation();
                const droppedKey = e.dataTransfer.getData('text/field_key');
                if (droppedKey) updateSubSlot(2, droppedKey);
              }}
              style={{
                fontSize: Math.min(30, Math.max(16, Math.round(box.h * 0.36))),
                fontWeight: 900,
                lineHeight: 1.05,
                marginTop: 2,
              }}
            >
              {bottomRight}
              {renderSubBadge(2, bottomRightKey, 'ヘッダー右下')}
            </div>
          </div>
        </div>
      );
    }

    if (box.box_type === 'energy_label_tv') {
      const starVal = parseFloat(String(specs.energy_star ?? rawVal ?? '2.5'));
      const starFormatted = Number.isNaN(starVal) ? '2.5' : starVal.toFixed(1);
      return (
        <div
          style={{
            flex: 1,
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            padding: 3,
            overflow: 'hidden',
          }}
        >
          <div style={{ color: '#009B4C', fontSize: 10.5, fontWeight: 900 }}>
            {box.title || '省エネ性能'}
          </div>
          <div style={{ color: '#EA5514', fontSize: 28, fontWeight: 900, lineHeight: 1.0 }}>
            {starFormatted}
          </div>
          <StarRatingRow rating={starFormatted} size={13} />
        </div>
      );
    }

    if (box.box_type === 'energy_label_unified') {
      return (
        <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
          <UnifiedEnergyLabelBox
            star={specs.energy_star || '2.1'}
            targetYear={specs.energy_target_year || '2021年度'}
            achievementPct={specs.energy_achievement_pct || '105'}
            annualKwh={specs.annual_power_kwh || '310'}
            annualBillYen={specs.annual_elec_bill_yen || '8,370'}
          />
        </div>
      );
    }

    if (box.box_type === 'door_diagram_3d') {
      const compartments = [1, 2, 3, 4, 5, 6].map((idx) => ({
        name: specs[`comp${idx}_name`] || '',
        capacity: specs[`comp${idx}_capacity_l`] || '',
        foodSpace: specs[`comp${idx}_food_space_l`] || '',
        badge: specs[`comp${idx}_badge`] || '',
      }));
      return (
        <div style={{ flex: 1, padding: 4, overflow: 'hidden' }}>
          <DoorDiagram3DWithDimensions
            doorLayout={String(specs[fk] || specs.door_layout || '扉3枚')}
            compartments={compartments}
            heightCm={specs.height_cm || '152.0'}
            widthCm={specs.width_cm || '54.0'}
            depthCm={specs.depth_cm || '65.5'}
            depthBodyOnlyCm={specs.depth_body_only_cm || '65.5'}
            showWidthBox={true}
            showFoodSpace={template.category === 'freezer'}
            totalCapacityL={specs.capacity_l || 200}
          />
        </div>
      );
    }

    if (box.box_type === 'door_swing_svg') {
      return (
        <div style={{ flex: 1, overflow: 'hidden' }}>
          <DoorSwingDiagramSvg
            openType={String(specs[fk] || specs.door_open_type || '右開き')}
            depthOpenCm={specs.depth_door_open_cm || '105.0'}
          />
        </div>
      );
    }

    if (box.box_type === 'e_angle_select') {
      return (
        <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
          <EAngleSelectPanel
            modelNo={String(specs.model_no || '')}
            baseModelNo={String(specs.base_model_no || '')}
            point1={String(specs.original_point_1 || 'オリジナル特典1')}
            point2={String(specs.original_point_2 || '')}
            point3={String(specs.original_point_3 || '')}
            makerName={String(specs.maker || 'Cymbal Retail')}
            compact={true}
          />
        </div>
      );
    }

    if (box.box_type === 'recycling_footer') {
      return (
        <div style={{ flex: 1, display: 'flex', alignItems: 'center', overflow: 'hidden' }}>
          <RecyclingFooterBar />
        </div>
      );
    }

    if (box.box_type === 'jan_barcode') {
      return (
        <div
          style={{
            flex: 1,
            padding: 6,
            display: 'flex',
            flexDirection: 'column',
            justifyContent: 'center',
            gap: 4,
            overflow: 'hidden',
          }}
        >
          <div style={{ fontSize: 9, fontWeight: 800, whiteSpace: 'nowrap' }}>
            {specs.color_name || '(W) ホワイト'}
          </div>
          <JanBarcodeSvg jan={String(specs[fk] || specs.jan_code || '4904530137310')} width={1.0} height={24} />
        </div>
      );
    }

    if (box.box_type === 'vod_grid') {
      return (
        <div
          style={{
            flex: 1,
            display: 'grid',
            gridTemplateColumns: '1fr 1fr',
            overflow: 'hidden',
          }}
        >
          {VOD_DEFS.map((v, idx) => {
            const active = ['〇', '○', '◯', 'O', '1', 'true'].includes(
              String(specs[v.key] ?? '〇').trim()
            );
            return (
              <div
                key={v.key}
                style={{
                  borderRight: idx % 2 === 0 ? '1px solid #CCC' : 'none',
                  borderBottom: idx < 8 ? '1px solid #CCC' : 'none',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontSize: 10.5,
                  fontWeight: 900,
                  color: v.color,
                  opacity: active ? 1 : 0.25,
                  whiteSpace: 'nowrap',
                }}
              >
                {v.label}
              </div>
            );
          })}
        </div>
      );
    }

    if (box.box_type === 'dimension_diagram') {
      return (
        <div
          style={{
            flex: 1,
            padding: 4,
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            overflow: 'hidden',
          }}
        >
          <div style={{ fontSize: 9.5, fontWeight: 800, whiteSpace: 'nowrap' }}>
            幅{specs.width_cm || specs.width_mm || '111.5'} × 高さ{specs.height_cm || specs.height_mm || '64.5'} × 奥行
            {specs.depth_cm || specs.depth_mm || '5.7'}
          </div>
          <svg viewBox="0 0 180 72" style={{ width: '92%', height: 64 }}>
            <rect x="34" y="8" width="96" height="48" fill="#B5B7B9" stroke="#333" strokeWidth="2" />
            <polygon points="72,56 92,56 104,64 60,64" fill="#444" />
            <rect x="148" y="8" width="6" height="48" fill="#444" />
          </svg>
          <div style={{ fontSize: 9, fontWeight: 800 }}>
            重さ: {specs.weight_kg || '16.5'}kg
          </div>
        </div>
      );
    }

    if (box.box_type === 'spec_table') {
      const subKeys =
        box.binding.sub_field_keys && box.binding.sub_field_keys.length > 0
          ? box.binding.sub_field_keys
          : [fk];
      const isFourGrid = subKeys.length >= 4;
      return (
        <div
          style={{
            flex: 1,
            display: 'grid',
            gridTemplateColumns: isFourGrid ? '1fr 1fr' : `repeat(${subKeys.length}, 1fr)`,
            overflow: 'hidden',
          }}
        >
          {subKeys.map((sk, idx) => {
            const sf = fieldByKey[sk];
            const sv = specs[sk] ?? '-';
            const shortLabel = sf ? sf.label.replace(/\(.*\)/, '').trim() : sk;
            return (
              <div
                key={sk}
                style={{
                  borderRight: isFourGrid
                    ? idx % 2 === 0
                      ? '1px solid #CCC'
                      : 'none'
                    : idx < subKeys.length - 1
                    ? '1px solid #CCC'
                    : 'none',
                  borderBottom: isFourGrid && idx < 2 ? '1px solid #CCC' : 'none',
                  padding: '2px 5px',
                  display: 'flex',
                  flexDirection: isFourGrid ? 'row' : 'column',
                  alignItems: 'center',
                  justifyContent: isFourGrid ? 'space-between' : 'center',
                  gap: 2,
                  overflow: 'hidden',
                }}
              >
                <span
                  style={{
                    fontSize: isFourGrid ? 8 : 8.5,
                    fontWeight: 700,
                    color: '#333',
                    whiteSpace: 'nowrap',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                  }}
                >
                  {shortLabel}
                </span>
                <span style={{ fontSize: isFourGrid ? 11.5 : 13, fontWeight: 900, whiteSpace: 'nowrap' }}>
                  {String(sv)}
                  {sf?.unit ? <span style={{ fontSize: 8.5, marginLeft: 1 }}>{sf.unit}</span> : null}
                </span>
              </div>
            );
          })}
        </div>
      );
    }

    if (box.box_type === 'point_callout') {
      return (
        <div
          style={{
            flex: 1,
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            padding: '0 8px',
            whiteSpace: 'nowrap',
            overflow: 'hidden',
          }}
        >
          <span style={{ color: '#595757', fontSize: 14, fontWeight: 800 }}>■ Point</span>
          <span style={{ fontSize: 17, fontWeight: 900, color: '#111111' }}>{valStr}</span>
        </div>
      );
    }

    if (box.box_type === 'boolean_badge') {
      const isOk = ['〇', '○', '◯', 'O', '1', 'true'].includes(valStr.trim());
      return (
        <div
          style={{
            flex: 1,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: Math.min(38, Math.max(20, Math.round((box.h - 24) * 0.55))),
            fontWeight: 800,
            color: box.value_color || '#111111',
          }}
        >
          {isOk ? '◯' : valStr === '×' ? '×' : valStr}
        </div>
      );
    }

    const isHero = box.box_type === 'hero_metric';
    const cleanValStr = unitStr ? valStr.replace(new RegExp(`${unitStr}$`), '').trim() : valStr;
    const computedSize =
      typeof box.value_font_size === 'number'
        ? box.value_font_size
        : computeAutoFontSize(cleanValStr, box.w, box.h, isHero, unitStr.length);

    return (
      <div
        style={{
          flex: 1,
          padding: '4px 6px',
          display: 'flex',
          flexDirection: 'column',
          alignItems:
            box.text_align === 'left'
              ? 'flex-start'
              : box.text_align === 'right'
              ? 'flex-end'
              : 'center',
          justifyContent: 'center',
          overflow: 'hidden',
          minWidth: 0,
        }}
      >
        {prefixStr && (
          <div
            style={{
              background: '#222222',
              color: '#FFFFFF',
              fontSize: 8.5,
              fontWeight: 700,
              padding: '1px 5px',
              marginBottom: 2,
              whiteSpace: 'nowrap',
            }}
          >
            {prefixStr}
          </div>
        )}
        <div
          style={{
            display: 'flex',
            alignItems: 'baseline',
            justifyContent: 'center',
            gap: 2,
            maxWidth: '100%',
            overflow: 'hidden',
          }}
        >
          <span
            style={{
              fontSize: computedSize,
              fontWeight: 800,
              lineHeight: 1.05,
              color: box.value_color || '#111111',
              textAlign: box.text_align || 'center',
              whiteSpace: isHero || cleanValStr.length <= 12 ? 'nowrap' : 'normal',
              wordBreak: 'break-word',
            }}
          >
            {cleanValStr}
          </span>
          {unitStr && (
            <span
              style={{
                fontSize: Math.max(10, Math.round(computedSize * 0.42)),
                fontWeight: 800,
                color: box.value_color || '#111111',
                whiteSpace: 'nowrap',
                flexShrink: 0,
              }}
            >
              {unitStr}
            </span>
          )}
        </div>
        {box.binding.sub_field_keys && box.binding.sub_field_keys.length > 0 && (
          <div
            style={{
              fontSize: 9.5,
              fontWeight: 700,
              color: '#333333',
              marginTop: 2,
              whiteSpace: 'nowrap',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              maxWidth: '100%',
            }}
          >
            {box.binding.sub_field_keys.map((sk) => specs[sk]).filter(Boolean).join(' / ')}
          </div>
        )}
      </div>
    );
  };

  const renderHeaderSlotBadge = (slotName: string, fieldKey: string, label: string) => {
    if (!interactive) return null;
    const isSel = selectedHeaderSlot === slotName;
    const isHigh = highlightedFieldKey && highlightedFieldKey === fieldKey;
    return (
      <span
        data-export-ignore="true"
        onClick={(e) => {
          e.stopPropagation();
          onSelectHeaderSlot(slotName);
          onSelectBox(null);
        }}
        style={{
          display: 'inline-block',
          marginLeft: 6,
          padding: '1px 6px',
          fontSize: 9.5,
          fontWeight: 800,
          borderRadius: 4,
          background: isSel || isHigh ? '#DC2626' : 'rgba(0,0,0,0.45)',
          color: '#FFFFFF',
          border: isSel || isHigh ? '1.5px solid #FEF08A' : '1px solid rgba(255,255,255,0.5)',
          cursor: 'pointer',
          verticalAlign: 'middle',
        }}
        title={`クリックしてヘッダー「${label}」の出力項目を変更（ドラッグ＆ドロップ可）`}
      >
        🎯 {fieldByKey[fieldKey]?.label || fieldKey || '未割当'}
      </span>
    );
  };

  const h = template.header;

  return (
    <div
      ref={canvasRef}
      onClick={() => {
        if (interactive) {
          onSelectBox(null);
          onSelectHeaderSlot(null);
        }
      }}
      style={{
        width: template.canvas_width,
        height: template.canvas_height,
        background: template.canvas_bg_color || '#EAEAEA',
        border: '2px solid #555555',
        position: 'relative',
        fontFamily: "'BIZ UDPGothic', sans-serif",
        color: '#111111',
        boxSizing: 'border-box',
        userSelect: 'none',
        overflow: 'hidden',
        boxShadow: '0 12px 32px rgba(15, 23, 42, 0.16)',
      }}
    >
      {/* Optional Reference Image Overlay for AI Vision Layout Verification */}
      {template.source_image_data_url && overlayOpacity > 0 && (
        <img
          data-export-ignore="true"
          src={template.source_image_data_url}
          alt="Reference Layout Overlay"
          style={{
            position: 'absolute',
            inset: 0,
            width: '100%',
            height: '100%',
            objectFit: 'fill',
            opacity: overlayOpacity,
            pointerEvents: 'none',
            zIndex: 40,
          }}
        />
      )}

      {/* Optional Editor Alignment Grid (Ignored on Export) */}
      {interactive && showGrid && (
        <div
          data-export-ignore="true"
          style={{
            position: 'absolute',
            inset: 0,
            backgroundImage:
              'linear-gradient(to right, rgba(37, 99, 235, 0.10) 1px, transparent 1px), linear-gradient(to bottom, rgba(37, 99, 235, 0.10) 1px, transparent 1px)',
            backgroundSize: '16px 16px',
            pointerEvents: 'none',
            zIndex: 5,
          }}
        />
      )}

      {/* TOP HEADER BAR */}
      {h.visible && (
        <div
          onClick={(e) => {
            if (!interactive) return;
            e.stopPropagation();
            onSelectHeaderSlot('header_main');
            onSelectBox(null);
          }}
          style={{
            position: 'absolute',
            top: 0,
            left: 0,
            width: '100%',
            height: h.height,
            background: h.default_bg_color || '#1B9E3E',
            color: h.text_color || '#FFFFFF',
            padding: '10px 20px',
            boxSizing: 'border-box',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            zIndex: 10,
            outline:
              interactive && selectedHeaderSlot
                ? '2.5px dashed #FACC15'
                : 'none',
          }}
        >
          {/* Left Header Area */}
          <div
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => {
              e.preventDefault();
              const fk = e.dataTransfer.getData('text/field_key');
              if (fk) onBindFieldToHeaderSlot('main_title_field_key', fk);
            }}
            style={{ minWidth: 0 }}
          >
            <div
              style={{
                fontSize: template.orientation === 'landscape' ? 38 : 28,
                fontWeight: 900,
                lineHeight: 1.05,
                whiteSpace: 'nowrap',
              }}
            >
              {resolveHeaderMainTitle()}
              {h.main_title_mode === 'field' &&
                renderHeaderSlotBadge('main_title_field_key', h.main_title_field_key, 'メインタイトル')}
            </div>
            {h.sub_left_field_key && (
              <div style={{ fontSize: 13, fontWeight: 700, marginTop: 3, whiteSpace: 'nowrap' }}>
                {String(specs[h.sub_left_field_key] || '')}
                {renderHeaderSlotBadge('sub_left_field_key', h.sub_left_field_key, '左サブ項目')}
              </div>
            )}
          </div>

          {/* Right Header Area: Maker + Brand + Model No (Directly matching user's screenshot arrows!) */}
          <div style={{ textAlign: 'left', whiteSpace: 'nowrap' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              {/* Top-Right Slot 1 (e.g. Maker SONY) */}
              <div
                onDragOver={(e) => e.preventDefault()}
                onDrop={(e) => {
                  e.preventDefault();
                  const fk = e.dataTransfer.getData('text/field_key');
                  if (fk) onBindFieldToHeaderSlot('top_right_1_field_key', fk);
                }}
                style={{
                  fontSize: 16,
                  fontWeight: 800,
                  padding: interactive ? '1px 4px' : 0,
                  borderRadius: 4,
                  border:
                    interactive &&
                    (selectedHeaderSlot === 'top_right_1_field_key' ||
                      highlightedFieldKey === h.top_right_1_field_key)
                      ? '2px solid #EF4444'
                      : 'none',
                }}
              >
                {h.top_right_1_field_key ? String(specs[h.top_right_1_field_key] ?? '') : ''}
                {renderHeaderSlotBadge('top_right_1_field_key', h.top_right_1_field_key, '右上①(メーカー等)')}
              </div>

              {/* Top-Right Slot 2 (e.g. Brand BRAVIA) */}
              <div
                onDragOver={(e) => e.preventDefault()}
                onDrop={(e) => {
                  e.preventDefault();
                  const fk = e.dataTransfer.getData('text/field_key');
                  if (fk) onBindFieldToHeaderSlot('top_right_2_field_key', fk);
                }}
                style={{
                  fontSize: 16,
                  fontWeight: 800,
                  padding: interactive ? '1px 4px' : 0,
                  borderRadius: 4,
                  border:
                    interactive &&
                    (selectedHeaderSlot === 'top_right_2_field_key' ||
                      highlightedFieldKey === h.top_right_2_field_key)
                      ? '2px solid #EF4444'
                      : 'none',
                }}
              >
                {h.top_right_2_field_key ? String(specs[h.top_right_2_field_key] ?? '') : ''}
                {renderHeaderSlotBadge('top_right_2_field_key', h.top_right_2_field_key, '右上②(ブランド等)')}
              </div>
            </div>

            {/* Bottom-Right Slot (e.g. Model No K50XR70M2) */}
            <div
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => {
                e.preventDefault();
                const fk = e.dataTransfer.getData('text/field_key');
                if (fk) onBindFieldToHeaderSlot('bottom_right_field_key', fk);
              }}
              style={{
                fontSize: template.orientation === 'landscape' ? 30 : 21,
                fontWeight: 900,
                lineHeight: 1.05,
                marginTop: 2,
                padding: interactive ? '1px 4px' : 0,
                borderRadius: 4,
                border:
                  interactive &&
                  (selectedHeaderSlot === 'bottom_right_field_key' ||
                    highlightedFieldKey === h.bottom_right_field_key)
                    ? '2px solid #EF4444'
                    : 'none',
              }}
            >
              {h.bottom_right_field_key ? String(specs[h.bottom_right_field_key] ?? '') : ''}
              {renderHeaderSlotBadge('bottom_right_field_key', h.bottom_right_field_key, '右下(型番等)')}
            </div>
          </div>
        </div>
      )}

      {/* MAIN CANVAS BOXES */}
      {template.boxes.map((box) => {
        const isSelected = interactive && selectedBoxId === box.id;
        const isFieldHighlighted =
          interactive &&
          highlightedFieldKey !== null &&
          (box.binding.field_key === highlightedFieldKey ||
            (box.binding.sub_field_keys || []).includes(highlightedFieldKey));

        return (
          <div
            key={box.id}
            onMouseDown={(e) => startBoxMouseAction(e, box, 'move')}
            onClick={(e) => {
              if (!interactive) return;
              e.stopPropagation();
              onSelectBox(box.id);
              onSelectHeaderSlot(null);
            }}
            onDragOver={(e) => {
              if (!interactive) return;
              e.preventDefault();
            }}
            onDrop={(e) => {
              if (!interactive) return;
              e.preventDefault();
              const fk = e.dataTransfer.getData('text/field_key');
              const fl = e.dataTransfer.getData('text/field_label');
              if (fk) {
                onBindFieldToBox(box.id, fk, fl || undefined);
              }
            }}
            style={{
              position: 'absolute',
              left: box.x,
              top: box.y,
              width: box.w,
              height: box.h,
              background: box.bg_color || '#FFFFFF',
              border: isSelected
                ? '2.5px solid #2563EB'
                : isFieldHighlighted
                ? '2.5px solid #DC2626'
                : `${box.border_width || 1.5}px solid ${box.border_color || '#999999'}`,
              borderRadius: box.border_radius || 0,
              boxSizing: 'border-box',
              display: 'flex',
              flexDirection: 'column',
              cursor: interactive ? 'move' : 'default',
              zIndex: isSelected ? 30 : isFieldHighlighted ? 25 : 15,
              boxShadow: isSelected
                ? '0 0 0 3px rgba(37, 99, 235, 0.25)'
                : isFieldHighlighted
                ? '0 0 0 4px rgba(220, 38, 38, 0.28)'
                : 'none',
              overflow: 'hidden',
            }}
          >
            {/* Optional Gray Header Bar */}
            {box.show_title_bar && (
              <div
                style={{
                  background: box.title_bg_color || '#666666',
                  color: box.title_text_color || '#FFFFFF',
                  height: 23,
                  fontSize: 11.5,
                  fontWeight: 700,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  padding: '0 4px',
                  whiteSpace: 'nowrap',
                  overflow: 'hidden',
                  flexShrink: 0,
                }}
              >
                <span
                  style={{
                    display: 'inline-block',
                    transform: (box.title || '').length >= 8 ? 'scaleX(0.86)' : 'none',
                    whiteSpace: 'nowrap',
                  }}
                >
                  {box.title}
                </span>
              </div>
            )}

            {/* Box Value / Widget Content */}
            {renderBoxBody(box)}

            {/* Interactive Field Binding Badge & Resize Handle (Ignored on Export) */}
            {interactive && (isSelected || isFieldHighlighted) && (
              <div
                data-export-ignore="true"
                style={{
                  position: 'absolute',
                  bottom: 2,
                  left: 2,
                  background: isFieldHighlighted ? '#DC2626' : '#2563EB',
                  color: '#FFFFFF',
                  fontSize: 8,
                  fontWeight: 800,
                  padding: '1px 5px',
                  borderRadius: 3,
                  pointerEvents: 'none',
                  whiteSpace: 'nowrap',
                  opacity: 0.92,
                }}
              >
                🔗 {box.binding.field_key} ({box.w}×{box.h})
              </div>
            )}

            {interactive && isSelected && (
              <div
                data-export-ignore="true"
                onMouseDown={(e) => startBoxMouseAction(e, box, 'resize')}
                title="ドラッグして枠のサイズを変更"
                style={{
                  position: 'absolute',
                  right: 0,
                  bottom: 0,
                  width: 13,
                  height: 13,
                  background: '#2563EB',
                  borderTopLeftRadius: 4,
                  cursor: 'nwse-resize',
                  zIndex: 35,
                }}
              />
            )}
          </div>
        );
      })}
    </div>
  );
};
