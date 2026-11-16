import React from 'react';
import { EAngleSelectPanel } from './SharedBannerParts';

/**
 * Automatically steps down font size when text length exceeds the target box capacity,
 * preventing overflow or unintended line wraps.
 */
function fitFontSize(
  text: string | number | undefined,
  baseSize: number,
  thresholdChars: number,
  minSize: number = 8
): number {
  const str = String(text ?? '');
  if (str.length <= thresholdChars) return baseSize;
  const ratio = thresholdChars / Math.max(1, str.length);
  return Math.max(minSize, Math.round(baseSize * Math.max(0.55, ratio) * 10) / 10);
}

export const PcBanner: React.FC<{ specs: Record<string, any> }> = ({ specs }) => {
  const cpuSeries = String(specs.cpu_series || 'Intel® Core™ Ultra7 155H');
  const isSnapdragon = cpuSeries.toLowerCase().includes('snapdragon');
  const isRyzen =
    cpuSeries.toLowerCase().includes('ryzen') || cpuSeries.toLowerCase().includes('amd');
  const isApple =
    cpuSeries.toLowerCase().includes('apple') ||
    cpuSeries.toLowerCase().includes('m3') ||
    cpuSeries.toLowerCase().includes('m4');

  const badgeBg = isSnapdragon
    ? 'linear-gradient(135deg, #B91C1C 0%, #7F1D1D 100%)'
    : isRyzen
    ? 'linear-gradient(135deg, #EA580C 0%, #9A3412 100%)'
    : isApple
    ? 'linear-gradient(135deg, #1F2937 0%, #111827 100%)'
    : 'linear-gradient(135deg, #1E3A8A 0%, #0F172A 100%)';

  const badgeBrand = isSnapdragon
    ? 'Snapdragon'
    : isRyzen
    ? 'AMD RYZEN'
    : isApple
    ? 'Apple Silicon'
    : 'intel CORE';

  const badgeSub = String(specs.cpu_badge_short || (isSnapdragon ? 'X2 Plus' : 'Ultra 7'));

  const hasEAngle = Boolean(
    (specs.base_model_no && String(specs.base_model_no).trim() !== '') ||
      (specs.original_point_1 && String(specs.original_point_1).trim() !== '')
  );

  const storageCapStr = String(specs.storage_capacity || '512GB');
  const storageNum = storageCapStr.replace(/[^0-9.]/g, '') || '512';
  const storageUnit = storageCapStr.replace(/[0-9.]/g, '') || 'GB';
  const memoryNum = String(specs.memory_gb || '16').replace(/[^0-9]/g, '') || '16';
  const weightStr = String(specs.weight_kg || '0.869');
  const officeStr =
    String(specs.office || '')
      .replace('【選択式】', '')
      .trim() || 'Microsoft 365 Personal (24か月版) ／ office H&B 2024 (永続版)';
  const graphicsStr = String(specs.graphics || 'インテル Arc グラフィックス');
  const refreshStr = String(specs.refresh_rate || '未公表');
  const driveStr = String(specs.optical_drive || 'なし');
  const mouseStr = String(specs.mouse || 'なし');
  const brandLogoStr = String(specs.brand_logo || 'FMV');
  const makerModelStr = `${specs.maker || 'FUJITSU'}  ${specs.model_no || 'FMVU77K3B5/W5'}`;
  const classNameStr = String(specs.class_name || 'モバイル高性能');
  const headerCatchStr = String(specs.header_catch || '家でも外でも使える');

  const cellHeader: React.CSSProperties = {
    background: '#666666',
    color: '#FFFFFF',
    fontWeight: 700,
    fontSize: 15,
    height: 28,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    textAlign: 'center',
    padding: '0 4px',
    lineHeight: 1,
    whiteSpace: 'nowrap',
    overflow: 'hidden',
    boxSizing: 'border-box',
    flexShrink: 0,
  };

  const subCellHeader: React.CSSProperties = {
    ...cellHeader,
    height: 25,
    fontSize: 12.5,
  };

  return (
    <div
      style={{
        width: hasEAngle ? 810 : 710,
        background: '#E6E6E6',
        border: '2px solid #555555',
        display: 'grid',
        gridTemplateColumns: hasEAngle ? '1fr 178px' : '1fr',
        fontFamily: "'BIZ UDPGothic', sans-serif",
        color: '#111111',
        boxSizing: 'border-box',
        userSelect: 'none',
        overflow: 'hidden',
      }}
    >
      {/* Left Main PC Banner */}
      <div style={{ display: 'flex', flexDirection: 'column', minWidth: 0, overflow: 'hidden' }}>
        {/* Navy Header (#1F4E78) */}
        <div
          style={{
            background: '#1F4E78',
            color: '#FFFFFF',
            padding: '14px 20px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 12,
            overflow: 'hidden',
          }}
        >
          <div style={{ minWidth: 0 }}>
            <div
              style={{
                fontSize: fitFontSize(brandLogoStr, 48, 8, 24),
                fontWeight: 900,
                letterSpacing: '0.08em',
                lineHeight: 1.0,
                whiteSpace: 'nowrap',
              }}
            >
              {brandLogoStr}
            </div>
            <div
              style={{
                fontSize: fitFontSize(makerModelStr, 17, 22, 11),
                fontWeight: 700,
                marginTop: 5,
                whiteSpace: 'nowrap',
              }}
            >
              {specs.maker || 'FUJITSU'}&nbsp;&nbsp;{specs.model_no || 'FMVU77K3B5/W5'}
            </div>
            <div style={{ fontSize: 11.5, marginTop: 3, opacity: 0.95, whiteSpace: 'nowrap' }}>
              発売日 {specs.release_date || '2025年11月13日'}
            </div>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexShrink: 0 }}>
            <div style={{ textAlign: 'right', whiteSpace: 'nowrap' }}>
              <div style={{ fontSize: fitFontSize(headerCatchStr, 14.5, 16, 10), fontWeight: 700 }}>
                {headerCatchStr}
              </div>
              <div
                style={{
                  fontSize: fitFontSize(specs.header_size_range || '14〜15インチ', 27, 10, 18),
                  fontWeight: 800,
                  lineHeight: 1.15,
                }}
              >
                {specs.header_size_range || '14〜15インチ'}
              </div>
              <div
                style={{
                  fontSize: fitFontSize(classNameStr, 13, 18, 9.5),
                  fontWeight: 700,
                  marginTop: 2,
                }}
              >
                {classNameStr}
              </div>
            </div>

            {/* Laptop Icon + Label */}
            <div
              style={{
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                flexShrink: 0,
              }}
            >
              <svg width="64" height="46" viewBox="0 0 68 48">
                <rect
                  x="10"
                  y="4"
                  width="48"
                  height="32"
                  rx="2"
                  fill="#1F4E78"
                  stroke="#FFFFFF"
                  strokeWidth="2.5"
                />
                <polygon points="2,44 66,44 58,36 10,36" fill="#FFFFFF" />
              </svg>
              <div
                style={{
                  fontSize: fitFontSize(specs.header_form_label || 'Homeモバイル ノートPC', 9, 14, 7),
                  lineHeight: 1.15,
                  marginTop: 3,
                  textAlign: 'center',
                  whiteSpace: 'nowrap',
                }}
              >
                {specs.header_form_label || 'Homeモバイル ノートPC'}
              </div>
            </div>
          </div>
        </div>

        {/* Spec Body */}
        <div style={{ padding: '10px 10px', display: 'flex', flexDirection: 'column', gap: 10 }}>
          {/* TOP SPEC ROW: CPU+NPU | Storage+Memory | Office */}
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: '248px 198px 1fr',
              gap: 8,
            }}
          >
            {/* CPU & NPU Box */}
            <div
              style={{
                background: '#FFFFFF',
                border: '1px solid #888888',
                display: 'grid',
                gridTemplateColumns: '158px 1fr',
                overflow: 'hidden',
              }}
            >
              {/* CPU */}
              <div
                style={{
                  borderRight: '1px solid #999999',
                  display: 'flex',
                  flexDirection: 'column',
                  minWidth: 0,
                  overflow: 'hidden',
                }}
              >
                <div style={cellHeader}>CPU</div>
                <div
                  style={{
                    flex: 1,
                    padding: '8px 7px 7px',
                    display: 'flex',
                    flexDirection: 'column',
                    justifyContent: 'space-between',
                    minWidth: 0,
                    overflow: 'hidden',
                  }}
                >
                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 6,
                      minWidth: 0,
                      overflow: 'hidden',
                    }}
                  >
                    <div
                      style={{
                        width: 54,
                        height: 54,
                        background: badgeBg,
                        color: '#FFFFFF',
                        padding: '4px 3px',
                        boxSizing: 'border-box',
                        display: 'flex',
                        flexDirection: 'column',
                        justifyContent: 'space-between',
                        fontWeight: 800,
                        lineHeight: 1.05,
                        flexShrink: 0,
                        overflow: 'hidden',
                      }}
                    >
                      <span
                        style={{
                          fontSize: fitFontSize(badgeBrand, 9, 7, 6.2),
                          whiteSpace: 'nowrap',
                        }}
                      >
                        {badgeBrand}
                      </span>
                      <span
                        style={{
                          fontSize: fitFontSize(badgeSub, 8, 7, 6),
                          opacity: 0.92,
                          whiteSpace: 'nowrap',
                        }}
                      >
                        {badgeSub.toUpperCase()}
                      </span>
                    </div>
                    <div
                      style={{
                        fontSize: fitFontSize(badgeSub, 22, 6, 14),
                        fontWeight: 800,
                        lineHeight: 1.05,
                        whiteSpace: 'nowrap',
                        minWidth: 0,
                        overflow: 'hidden',
                      }}
                    >
                      {badgeSub}
                    </div>
                  </div>
                  <div
                    style={{
                      fontSize: fitFontSize(cpuSeries, 10.5, 19, 7.8),
                      fontWeight: 700,
                      marginTop: 6,
                      whiteSpace: 'nowrap',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                    }}
                  >
                    {cpuSeries}
                  </div>
                </div>
              </div>

              {/* NPU */}
              <div
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  minWidth: 0,
                  overflow: 'hidden',
                }}
              >
                <div style={cellHeader}>NPU</div>
                <div
                  style={{
                    flex: 1,
                    padding: '6px 4px',
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    minWidth: 0,
                    overflow: 'hidden',
                  }}
                >
                  {['○', '〇', '◯'].includes(String(specs.copilot_plus || '○')) ? (
                    <div
                      style={{
                        background: '#222222',
                        color: '#FFFFFF',
                        fontSize: 7.8,
                        fontWeight: 700,
                        padding: '2px 2px',
                        width: '100%',
                        textAlign: 'center',
                        boxSizing: 'border-box',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      Copilot+ PC準拠
                    </div>
                  ) : (
                    <div style={{ height: 15 }} />
                  )}
                  <div
                    style={{
                      fontSize: fitFontSize(specs.npu_tops || '45', 46, 2, 28),
                      fontWeight: 700,
                      lineHeight: 0.95,
                      marginTop: 2,
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {specs.npu_tops || '45'}
                  </div>
                  <div
                    style={{
                      fontSize: 14,
                      fontWeight: 700,
                      alignSelf: 'flex-end',
                      paddingRight: 2,
                      whiteSpace: 'nowrap',
                    }}
                  >
                    TOPS
                  </div>
                </div>
              </div>
            </div>

            {/* Storage & Memory Box (Strictly separated so numbers NEVER overlap) */}
            <div
              style={{
                background: '#FFFFFF',
                border: '1px solid #888888',
                display: 'grid',
                gridTemplateColumns: '112px 1fr',
                overflow: 'hidden',
              }}
            >
              {/* Storage */}
              <div
                style={{
                  borderRight: '1px solid #999999',
                  display: 'flex',
                  flexDirection: 'column',
                  minWidth: 0,
                  overflow: 'hidden',
                }}
              >
                <div style={cellHeader}>ストレージ</div>
                <div
                  style={{
                    flex: 1,
                    padding: '6px 6px',
                    display: 'flex',
                    flexDirection: 'column',
                    justifyContent: 'space-between',
                    minWidth: 0,
                    overflow: 'hidden',
                  }}
                >
                  <div
                    style={{
                      background: '#222222',
                      color: '#FFFFFF',
                      fontSize: 10.5,
                      fontWeight: 700,
                      padding: '1px 6px',
                      alignSelf: 'flex-start',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {specs.storage_type || 'SSD'}
                  </div>
                  <div
                    style={{
                      fontSize: fitFontSize(storageNum, 42, 3, 28),
                      fontWeight: 700,
                      lineHeight: 0.95,
                      textAlign: 'center',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {storageNum}
                  </div>
                  <div
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'baseline',
                      gap: 2,
                      whiteSpace: 'nowrap',
                    }}
                  >
                    <span
                      style={{
                        fontSize: fitFontSize(specs.storage_note || '(NVMe)', 9.5, 7, 7),
                        fontWeight: 700,
                      }}
                    >
                      {specs.storage_note || '(NVMe)'}
                    </span>
                    <span style={{ fontSize: 14.5, fontWeight: 700 }}>{storageUnit}</span>
                  </div>
                </div>
              </div>

              {/* Memory */}
              <div
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  minWidth: 0,
                  overflow: 'hidden',
                }}
              >
                <div style={cellHeader}>メモリ</div>
                <div
                  style={{
                    flex: 1,
                    padding: '6px 5px',
                    display: 'flex',
                    flexDirection: 'column',
                    justifyContent: 'flex-end',
                    alignItems: 'center',
                    minWidth: 0,
                    overflow: 'hidden',
                  }}
                >
                  <div
                    style={{
                      fontSize: fitFontSize(memoryNum, 42, 2, 28),
                      fontWeight: 700,
                      lineHeight: 0.95,
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {memoryNum}
                  </div>
                  <div
                    style={{
                      fontSize: 14.5,
                      fontWeight: 700,
                      alignSelf: 'flex-end',
                      marginTop: 4,
                      whiteSpace: 'nowrap',
                    }}
                  >
                    GB
                  </div>
                </div>
              </div>
            </div>

            {/* Office Box */}
            <div
              style={{
                background: '#FFFFFF',
                border: '1px solid #888888',
                display: 'flex',
                flexDirection: 'column',
                minWidth: 0,
                overflow: 'hidden',
              }}
            >
              <div style={cellHeader}>Office</div>
              <div
                style={{
                  flex: 1,
                  padding: '6px 7px',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 5,
                  minWidth: 0,
                  overflow: 'hidden',
                }}
              >
                <div
                  style={{
                    border: '1px solid #666666',
                    textAlign: 'center',
                    fontSize: 11,
                    fontWeight: 700,
                    padding: '1px 4px',
                    whiteSpace: 'nowrap',
                  }}
                >
                  {specs.office_type || '選択式'}
                </div>
                <div
                  style={{
                    fontSize: fitFontSize(officeStr, 11, 48, 8.5),
                    fontWeight: 700,
                    lineHeight: 1.28,
                    overflow: 'hidden',
                  }}
                >
                  {officeStr}
                </div>
              </div>
            </div>
          </div>

          {/* BOTTOM SPEC ROW: Display + Refresh + GPU | Weight + Drive + Mouse + Battery */}
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: '334px 1fr',
              gap: 8,
            }}
          >
            {/* Left: Display | Refresh Rate | Graphics */}
            <div
              style={{
                background: '#FFFFFF',
                border: '1px solid #888888',
                display: 'grid',
                gridTemplateColumns: '110px 112px 1fr',
                overflow: 'hidden',
              }}
            >
              {/* Display */}
              <div
                style={{
                  borderRight: '1px solid #999999',
                  display: 'flex',
                  flexDirection: 'column',
                  minWidth: 0,
                  overflow: 'hidden',
                }}
              >
                <div style={subCellHeader}>ディスプレイ</div>
                <div
                  style={{
                    flex: 1,
                    padding: '7px 5px 6px',
                    display: 'flex',
                    flexDirection: 'column',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    minWidth: 0,
                    overflow: 'hidden',
                  }}
                >
                  <div
                    style={{
                      fontSize: 35,
                      fontWeight: 700,
                      lineHeight: 1.0,
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {Number(specs.display_inch || 14).toFixed(1)}
                  </div>
                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      width: '100%',
                      gap: 2,
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {['○', '〇', '◯'].includes(String(specs.touch_support || '○')) ? (
                      <span
                        style={{
                          background: '#222222',
                          color: '#FFFFFF',
                          fontSize: 8,
                          fontWeight: 700,
                          padding: '2px 3px',
                          whiteSpace: 'nowrap',
                          flexShrink: 0,
                        }}
                      >
                        タッチモデル
                      </span>
                    ) : (
                      <span />
                    )}
                    <span
                      style={{
                        fontSize: 11.5,
                        fontWeight: 700,
                        whiteSpace: 'nowrap',
                        flexShrink: 0,
                      }}
                    >
                      インチ
                    </span>
                  </div>
                  <div
                    style={{
                      fontSize: fitFontSize(specs.display_pixels || '1920×1200', 13.5, 9, 10),
                      fontWeight: 700,
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {specs.display_pixels || '1920×1200'}
                  </div>
                </div>
              </div>

              {/* Refresh Rate (Identical 25px header height & 12.5px vertical font size with condensed horizontal width) */}
              <div
                style={{
                  borderRight: '1px solid #999999',
                  display: 'flex',
                  flexDirection: 'column',
                  minWidth: 0,
                  overflow: 'hidden',
                }}
              >
                <div style={subCellHeader}>
                  <span
                    style={{
                      display: 'inline-block',
                      transform: 'scaleX(0.85)',
                      transformOrigin: 'center center',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    リフレッシュレート
                  </span>
                </div>
                <div
                  style={{
                    flex: 1,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontSize: fitFontSize(refreshStr, 18, 5, 11),
                    fontWeight: 700,
                    padding: '0 4px',
                    textAlign: 'center',
                    whiteSpace: 'nowrap',
                  }}
                >
                  {refreshStr}
                </div>
              </div>

              {/* Graphics */}
              <div
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  minWidth: 0,
                  overflow: 'hidden',
                }}
              >
                <div style={subCellHeader}>グラフィックス</div>
                <div
                  style={{
                    flex: 1,
                    padding: '6px 6px',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontSize: fitFontSize(graphicsStr, 12, 18, 9),
                    fontWeight: 700,
                    lineHeight: 1.25,
                    overflow: 'hidden',
                  }}
                >
                  {graphicsStr}
                </div>
              </div>
            </div>

            {/* Right: Weight + Drive + Mouse (Top) & Battery (Bottom) */}
            <div
              style={{
                background: '#FFFFFF',
                border: '1px solid #888888',
                display: 'flex',
                flexDirection: 'column',
                minWidth: 0,
                overflow: 'hidden',
              }}
            >
              {/* Top sub-row */}
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: '88px 1fr 68px',
                  borderBottom: '1px solid #999999',
                }}
              >
                <div style={{ borderRight: '1px solid #999999', minWidth: 0, overflow: 'hidden' }}>
                  <div style={subCellHeader}>
                    重量<span style={{ fontSize: 9.5, marginLeft: 1 }}>(約)</span>
                  </div>
                  <div
                    style={{
                      height: 40,
                      display: 'flex',
                      alignItems: 'baseline',
                      justifyContent: 'center',
                      paddingTop: 6,
                      whiteSpace: 'nowrap',
                    }}
                  >
                    <span
                      style={{
                        fontSize: fitFontSize(weightStr, 22, 4, 16),
                        fontWeight: 700,
                      }}
                    >
                      {weightStr}
                    </span>
                    <span style={{ fontSize: 11, fontWeight: 700, marginLeft: 1 }}>kg</span>
                  </div>
                </div>

                <div style={{ borderRight: '1px solid #999999', minWidth: 0, overflow: 'hidden' }}>
                  <div style={subCellHeader}>
                    <span
                      style={{
                        display: 'inline-block',
                        transform: 'scaleX(0.92)',
                        transformOrigin: 'center center',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      DVD/BDドライブ
                    </span>
                  </div>
                  <div
                    style={{
                      height: 40,
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      fontSize: fitFontSize(driveStr, 16, 6, 10),
                      fontWeight: 700,
                      whiteSpace: 'nowrap',
                      padding: '0 4px',
                    }}
                  >
                    {driveStr}
                  </div>
                </div>

                <div style={{ minWidth: 0, overflow: 'hidden' }}>
                  <div style={subCellHeader}>マウス</div>
                  <div
                    style={{
                      height: 40,
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      fontSize: fitFontSize(mouseStr, 16, 4, 10),
                      fontWeight: 700,
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {mouseStr}
                  </div>
                </div>
              </div>

              {/* Bottom sub-row: Battery */}
              <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
                <div style={subCellHeader}>
                  バッテリー駆動時間<span style={{ fontSize: 9.5, marginLeft: 2 }}>(約) (JEITA 3.0)</span>
                </div>
                <div
                  style={{
                    flex: 1,
                    display: 'grid',
                    gridTemplateColumns: '1fr 1fr',
                    alignItems: 'center',
                    padding: '4px 6px',
                  }}
                >
                  <div
                    style={{
                      borderRight: '1px solid #999999',
                      display: 'flex',
                      alignItems: 'baseline',
                      justifyContent: 'center',
                      gap: 2,
                      whiteSpace: 'nowrap',
                    }}
                  >
                    <span style={{ fontSize: 9.5, fontWeight: 700 }}>動画再生時</span>
                    <span
                      style={{
                        fontSize: fitFontSize(specs.battery_video_hours || '13.5', 25, 4, 18),
                        fontWeight: 700,
                      }}
                    >
                      {specs.battery_video_hours || '13.5'}
                    </span>
                    <span style={{ fontSize: 9.5, fontWeight: 700 }}>時間</span>
                  </div>
                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'baseline',
                      justifyContent: 'center',
                      gap: 2,
                      whiteSpace: 'nowrap',
                    }}
                  >
                    <span style={{ fontSize: 9.5, fontWeight: 700 }}>アイドル時</span>
                    <span
                      style={{
                        fontSize: fitFontSize(specs.battery_idle_hours || '35.0', 25, 4, 18),
                        fontWeight: 700,
                      }}
                    >
                      {specs.battery_idle_hours || '35.0'}
                    </span>
                    <span style={{ fontSize: 9.5, fontWeight: 700 }}>時間</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Right Orange e angle Select Panel */}
      {hasEAngle && (
        <EAngleSelectPanel
          modelNo={String(specs.model_no || '')}
          baseModelNo={String(specs.base_model_no || '')}
          headline={String(specs.original_point_headline || '買った後も安心')}
          point1={String(specs.original_point_1 || '')}
          point2={String(specs.original_point_2 || '')}
          point3={String(specs.original_point_3 || '')}
          makerName={String(specs.maker || '富士通')}
          compact={true}
        />
      )}
    </div>
  );
};
