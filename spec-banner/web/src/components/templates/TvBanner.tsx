import React from 'react';
import { StarRatingRow } from './SharedBannerParts';

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

const VOD_ITEMS: Array<{
  key: string;
  label: string;
  subLabel?: string;
  color: string;
  weight?: number;
}> = [
  { key: 'vod_netflix', label: 'NETFLIX', color: '#E50914', weight: 900 },
  { key: 'vod_youtube', label: 'YouTube', color: '#FF0000', weight: 900 },
  { key: 'vod_unext', label: 'U-NEXT', color: '#005BAC', weight: 900 },
  { key: 'vod_tver', label: 'TVer', color: '#0095D9', weight: 900 },
  {
    key: 'vod_prime',
    label: 'Prime Video',
    subLabel: 'amazon',
    color: '#0073BB',
    weight: 800,
  },
  { key: 'vod_abema', label: 'ABEMA', color: '#111111', weight: 900 },
  { key: 'vod_disney', label: 'Disney+', color: '#113CCF', weight: 900 },
  { key: 'vod_dazn', label: 'DAZN', color: '#111111', weight: 900 },
  { key: 'vod_hulu', label: 'hulu', color: '#1CE783', weight: 900 },
  { key: 'vod_lemino', label: 'Lemino', color: '#E60033', weight: 900 },
];

export const TvBanner: React.FC<{ specs: Record<string, any> }> = ({ specs }) => {
  const tvType = String(specs.type || 'MiniLED');
  let headerBg = '#1B9E3E';
  let headerTitle = 'Mini LED テレビ';
  if (tvType === '2K液晶') {
    headerBg = '#0075C2';
    headerTitle = '2K液晶テレビ';
  } else if (tvType === '4K液晶') {
    headerBg = '#0075C2';
    headerTitle = '4K液晶テレビ';
  } else if (tvType === '有機EL') {
    headerBg = '#000000';
    headerTitle = '有機ELテレビ';
  }

  const isSupported = (v: any) =>
    ['〇', '○', '◯', 'O', 'true', '1'].includes(String(v || '〇').trim());

  const cellHeaderStyle: React.CSSProperties = {
    background: '#666666',
    color: '#FFFFFF',
    fontWeight: 700,
    fontSize: 12,
    height: 22,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    textAlign: 'center',
    padding: '0 4px',
    lineHeight: 1.15,
    whiteSpace: 'nowrap',
    boxSizing: 'border-box',
  };

  const targetYearStr = String(specs.energy_target_year || '2026年度').includes('年度')
    ? String(specs.energy_target_year || '2026年度')
    : `${specs.energy_target_year}年度`;

  const formattedStar = (() => {
    const n = parseFloat(String(specs.energy_star || '2.5'));
    return Number.isNaN(n) ? String(specs.energy_star || '2.5') : n.toFixed(1);
  })();

  return (
    <div
      style={{
        width: 820,
        background: '#EAEAEA',
        border: '2px solid #999999',
        fontFamily: "'BIZ UDPGothic', sans-serif",
        color: '#111111',
        boxSizing: 'border-box',
        userSelect: 'none',
        overflow: 'hidden',
      }}
    >
      {/* Top Dynamic Color Header */}
      <div
        style={{
          background: headerBg,
          color: '#FFFFFF',
          padding: '14px 26px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 16,
        }}
      >
        <div
          style={{
            fontSize: 46,
            fontWeight: 900,
            letterSpacing: '0.02em',
            lineHeight: 1.05,
            whiteSpace: 'nowrap',
          }}
        >
          {headerTitle}
        </div>
        <div style={{ textAlign: 'left', minWidth: 280, whiteSpace: 'nowrap' }}>
          <div
            style={{
              fontSize: 19,
              fontWeight: 800,
              letterSpacing: '0.05em',
              lineHeight: 1.1,
            }}
          >
            {specs.maker || 'SONY'}&nbsp;&nbsp;{specs.brand || ''}
          </div>
          <div
            style={{
              fontSize: fitFontSize(specs.model_no || 'K50XR70M2', 40, 11, 24),
              fontWeight: 900,
              letterSpacing: '0.02em',
              lineHeight: 1.05,
              marginTop: 2,
            }}
          >
            {specs.model_no || 'K50XR70M2'}
          </div>
        </div>
      </div>

      {/* Main 3-Column Body */}
      <div
        style={{
          padding: 12,
          display: 'grid',
          gridTemplateColumns: '352px 190px 1fr',
          gap: 10,
        }}
      >
        {/* LEFT COLUMN */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10, minWidth: 0 }}>
          {/* Giant Screen Size Box */}
          <div
            style={{
              background: '#FFFFFF',
              border: '1px solid #B5B5B5',
              flex: 1,
              display: 'flex',
              flexDirection: 'column',
            }}
          >
            <div style={cellHeaderStyle}>画面サイズ</div>
            <div
              style={{
                flex: 1,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                padding: '12px 14px',
                gap: 14,
                whiteSpace: 'nowrap',
              }}
            >
              <span
                style={{
                  fontSize: 168,
                  fontWeight: 500,
                  lineHeight: 0.92,
                  letterSpacing: '-0.02em',
                  color: '#000000',
                  flexShrink: 0,
                }}
              >
                {specs.screen_size || 50}
              </span>
              <div
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  justifyContent: 'flex-end',
                  alignSelf: 'flex-end',
                  paddingBottom: 12,
                  lineHeight: 1.05,
                  flexShrink: 0,
                }}
              >
                <span style={{ fontSize: 58, fontWeight: 500 }}>V</span>
                <span style={{ fontSize: 48, fontWeight: 500 }}>型</span>
              </div>
            </div>
          </div>

          {/* 2x2 Grid: Display Method, Double Speed, Smart TV, Dual Screen */}
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: '1fr 1fr',
              gap: 10,
            }}
          >
            <div style={{ background: '#FFFFFF', border: '1px solid #B5B5B5' }}>
              <div style={cellHeaderStyle}>ディスプレイ方式</div>
              <div
                style={{
                  height: 68,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontSize: fitFontSize(specs.display_method || '量子Dot', 27, 6, 14),
                  fontWeight: 900,
                  whiteSpace: 'nowrap',
                  padding: '0 4px',
                }}
              >
                {specs.display_method || '量子Dot'}
              </div>
            </div>

            <div style={{ background: '#FFFFFF', border: '1px solid #B5B5B5' }}>
              <div style={cellHeaderStyle}>倍速機能</div>
              <div
                style={{
                  height: 68,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontSize: 40,
                  fontWeight: 700,
                }}
              >
                {specs.double_speed || '×'}
              </div>
            </div>

            <div style={{ background: '#FFFFFF', border: '1px solid #B5B5B5' }}>
              <div style={cellHeaderStyle}>スマートTV</div>
              <div
                style={{
                  height: 68,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontSize: fitFontSize(specs.smart_tv || 'Google TV', 25, 9, 13),
                  fontWeight: 900,
                  color: '#0062B1',
                  textAlign: 'center',
                  padding: '0 4px',
                  whiteSpace: 'nowrap',
                }}
              >
                {specs.smart_tv || 'Google TV'}
              </div>
            </div>

            <div style={{ background: '#FFFFFF', border: '1px solid #B5B5B5' }}>
              <div style={cellHeaderStyle}>2画面機能</div>
              <div
                style={{
                  height: 68,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontSize: 40,
                  fontWeight: 700,
                }}
              >
                {specs.dual_screen || '×'}
              </div>
            </div>
          </div>
        </div>

        {/* MIDDLE COLUMN */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6, minWidth: 0 }}>
          {/* Resolution + Recording */}
          <div
            style={{
              background: '#FFFFFF',
              border: '1px solid #B5B5B5',
              display: 'grid',
              gridTemplateColumns: '1fr 1fr',
            }}
          >
            <div style={{ borderRight: '1px solid #CCCCCC', minWidth: 0 }}>
              <div style={cellHeaderStyle}>画素数</div>
              <div
                style={{
                  height: 44,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontSize: 13.5,
                  fontWeight: 800,
                  whiteSpace: 'nowrap',
                }}
              >
                {specs.resolution || '3840×2160'}
              </div>
            </div>
            <div style={{ minWidth: 0 }}>
              <div style={cellHeaderStyle}>録画機能</div>
              <div
                style={{
                  height: 44,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontSize: 9.5,
                  fontWeight: 800,
                  textAlign: 'center',
                  lineHeight: 1.2,
                  padding: '0 3px',
                }}
              >
                {specs.recording || '外付けHDD、W録画対応'}
              </div>
            </div>
          </div>

          {/* Recommended Tatami */}
          <div style={{ background: '#FFFFFF', border: '1px solid #B5B5B5' }}>
            <div style={cellHeaderStyle}>おすすめ畳数</div>
            <div
              style={{
                height: 52,
                display: 'flex',
                alignItems: 'baseline',
                justifyContent: 'center',
                paddingTop: 4,
                whiteSpace: 'nowrap',
              }}
            >
              <span style={{ fontSize: 40, fontWeight: 800, lineHeight: 1 }}>
                {String(specs.recommended_tatami || '10畳程度').replace(/畳.*/, '')}
              </span>
              <span style={{ fontSize: 21, fontWeight: 800, marginLeft: 2 }}>畳程度</span>
            </div>
          </div>

          {/* Viewing Distance */}
          <div style={{ background: '#FFFFFF', border: '1px solid #B5B5B5' }}>
            <div style={cellHeaderStyle}>視聴距離 目安</div>
            <div
              style={{
                height: 52,
                display: 'flex',
                alignItems: 'baseline',
                justifyContent: 'center',
                gap: 2,
                paddingTop: 4,
                whiteSpace: 'nowrap',
              }}
            >
              <span style={{ fontSize: 21, fontWeight: 700 }}>約</span>
              <span style={{ fontSize: 40, fontWeight: 800, lineHeight: 1 }}>
                {String(specs.viewing_distance || '1.0')
                  .replace(/約/g, '')
                  .replace(/m.*/g, '')
                  .trim() || '1.0'}
              </span>
              <span style={{ fontSize: 23, fontWeight: 700 }}>m~</span>
            </div>
          </div>

          {/* VOD 2x5 Grid */}
          <div style={{ background: '#FFFFFF', border: '1px solid #B5B5B5' }}>
            <div style={cellHeaderStyle}>ネット動画コンテンツ対応※</div>
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: '1fr 1fr',
              }}
            >
              {VOD_ITEMS.map((vod, idx) => {
                const active = isSupported(specs[vod.key]);
                return (
                  <div
                    key={vod.key}
                    style={{
                      height: 31,
                      borderRight: idx % 2 === 0 ? '1px solid #CCCCCC' : 'none',
                      borderBottom: idx < 8 ? '1px solid #CCCCCC' : 'none',
                      display: 'flex',
                      flexDirection: 'column',
                      alignItems: 'center',
                      justifyContent: 'center',
                      opacity: active ? 1 : 0.25,
                      position: 'relative',
                      whiteSpace: 'nowrap',
                      overflow: 'hidden',
                    }}
                  >
                    {vod.subLabel && (
                      <span
                        style={{
                          fontSize: 7.5,
                          fontWeight: 700,
                          color: vod.color,
                          lineHeight: 0.9,
                          whiteSpace: 'nowrap',
                        }}
                      >
                        {vod.subLabel}
                      </span>
                    )}
                    <span
                      style={{
                        fontSize: vod.subLabel ? 11 : 12.5,
                        fontWeight: vod.weight || 900,
                        color: vod.key === 'vod_hulu' ? '#00A850' : vod.color,
                        letterSpacing: '-0.02em',
                        lineHeight: 1.05,
                        whiteSpace: 'nowrap',
                      }}
                    >
                      {vod.label}
                    </span>
                    {!active && (
                      <span
                        style={{
                          position: 'absolute',
                          color: '#333',
                          fontSize: 20,
                          fontWeight: 900,
                        }}
                      >
                        ×
                      </span>
                    )}
                  </div>
                );
              })}
            </div>
          </div>

          <div
            style={{
              fontSize: 7.8,
              lineHeight: 1.25,
              textAlign: 'center',
              color: '#222',
              whiteSpace: 'nowrap',
            }}
          >
            ※発売時点の対応コンテンツとなります
            <br />
            サービスは予告なく終了する場合があります
          </div>

          {/* Built-in Tuners 2x2 */}
          <div style={{ background: '#FFFFFF', border: '1px solid #B5B5B5' }}>
            <div style={cellHeaderStyle}>内蔵チューナー</div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', fontSize: 10.5 }}>
              <div
                style={{
                  borderRight: '1px solid #CCC',
                  borderBottom: '1px solid #CCC',
                  padding: '3px 5px',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  fontWeight: 700,
                  whiteSpace: 'nowrap',
                }}
              >
                <span style={{ fontSize: 9 }}>地上デジタル</span>
                <span style={{ fontSize: 14.5, fontWeight: 900 }}>
                  {specs.tuner_terrestrial ?? 3}
                </span>
              </div>
              <div
                style={{
                  borderBottom: '1px solid #CCC',
                  padding: '3px 5px',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  fontWeight: 700,
                  whiteSpace: 'nowrap',
                }}
              >
                <span style={{ fontSize: 8.5 }}>BS・110度CS</span>
                <span style={{ fontSize: 14.5, fontWeight: 900 }}>{specs.tuner_bs_cs ?? 3}</span>
              </div>
              <div
                style={{
                  borderRight: '1px solid #CCC',
                  padding: '3px 5px',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  fontWeight: 700,
                  whiteSpace: 'nowrap',
                }}
              >
                <span style={{ fontSize: 8 }}>BS・110度CS 4K</span>
                <span style={{ fontSize: 14.5, fontWeight: 900 }}>{specs.tuner_bs4k ?? 3}</span>
              </div>
              <div
                style={{
                  padding: '3px 5px',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  fontWeight: 700,
                  whiteSpace: 'nowrap',
                }}
              >
                <span style={{ fontSize: 9 }}>BS 8K</span>
                <span style={{ fontSize: 14.5, fontWeight: 900 }}>{specs.tuner_bs8k ?? 0}</span>
              </div>
            </div>
          </div>
        </div>

        {/* RIGHT COLUMN */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6, minWidth: 0 }}>
          {/* Top Row: Energy Star + Power Consumption W */}
          <div style={{ display: 'grid', gridTemplateColumns: '132px 1fr', gap: 6 }}>
            <div
              style={{
                background: '#FFFFFF',
                border: '2.5px solid #009B4C',
                padding: '3px 4px',
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
                whiteSpace: 'nowrap',
                overflow: 'hidden',
              }}
            >
              <div style={{ color: '#009B4C', fontSize: 10.5, fontWeight: 900 }}>省エネ性能</div>
              <div
                style={{
                  color: '#EA5514',
                  fontSize: 31,
                  fontWeight: 900,
                  lineHeight: 1.0,
                  margin: '2px 0',
                }}
              >
                {formattedStar}
              </div>
              <StarRatingRow rating={formattedStar} size={14} />
            </div>

            <div
              style={{
                background: '#FFFFFF',
                border: '1px solid #B5B5B5',
                display: 'flex',
                flexDirection: 'column',
              }}
            >
              <div style={cellHeaderStyle}>消費電力</div>
              <div
                style={{
                  flex: 1,
                  display: 'flex',
                  alignItems: 'baseline',
                  justifyContent: 'center',
                  paddingTop: 10,
                  whiteSpace: 'nowrap',
                }}
              >
                <span style={{ fontSize: 27, fontWeight: 800 }}>
                  {specs.power_consumption_w || 180}
                </span>
                <span style={{ fontSize: 16, fontWeight: 800, marginLeft: 2 }}>W</span>
              </div>
            </div>
          </div>

          {/* Energy Achievement + Annual Power */}
          <div
            style={{
              background: '#FFFFFF',
              border: '1px solid #B5B5B5',
              display: 'grid',
              gridTemplateColumns: '64px 70px 1fr',
            }}
          >
            <div
              style={{
                borderRight: '1px solid #CCC',
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
                padding: '3px 2px',
                whiteSpace: 'nowrap',
              }}
            >
              <div
                style={{
                  width: 28,
                  height: 28,
                  borderRadius: '50%',
                  background: '#009B4C',
                  color: '#FFFFFF',
                  fontWeight: 900,
                  fontSize: 18,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                }}
              >
                e
              </div>
              <div
                style={{
                  fontSize: 8,
                  fontWeight: 800,
                  textAlign: 'center',
                  lineHeight: 1.15,
                  marginTop: 2,
                  whiteSpace: 'nowrap',
                }}
              >
                目標年度
                <br />
                {targetYearStr}
              </div>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column' }}>
              <div
                style={{
                  ...cellHeaderStyle,
                  height: 'auto',
                  padding: '3px 4px',
                  flex: 1,
                  borderBottom: '1px solid #FFF',
                  fontSize: 9,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                }}
              >
                省エネ基準
                <br />
                達成率
              </div>
              <div
                style={{
                  ...cellHeaderStyle,
                  height: 'auto',
                  padding: '3px 4px',
                  flex: 1,
                  fontSize: 9,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                }}
              >
                年間消費
                <br />
                電力量
              </div>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', minWidth: 0 }}>
              <div
                style={{
                  flex: 1,
                  borderBottom: '1px solid #CCC',
                  display: 'flex',
                  alignItems: 'baseline',
                  justifyContent: 'center',
                  paddingTop: 2,
                  whiteSpace: 'nowrap',
                }}
              >
                <span style={{ fontSize: 21, fontWeight: 800 }}>
                  {specs.energy_achievement_pct || 103}
                </span>
                <span style={{ fontSize: 12, fontWeight: 800, marginLeft: 1 }}>%</span>
              </div>
              <div
                style={{
                  flex: 1,
                  display: 'flex',
                  alignItems: 'baseline',
                  justifyContent: 'center',
                  paddingTop: 2,
                  whiteSpace: 'nowrap',
                }}
              >
                <span style={{ fontSize: 19, fontWeight: 800 }}>
                  {specs.annual_power_kwh || 129}
                </span>
                <span style={{ fontSize: 9.5, fontWeight: 800, marginLeft: 1 }}>kWh/年</span>
              </div>
            </div>
          </div>

          {/* Annual Electricity Bill */}
          <div
            style={{
              background: '#FFFFFF',
              border: '1px solid #B5B5B5',
              display: 'grid',
              gridTemplateColumns: '122px 1fr',
            }}
          >
            <div
              style={{
                ...cellHeaderStyle,
                height: 'auto',
                padding: '3px 4px',
                fontSize: 9,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                lineHeight: 1.2,
              }}
            >
              1年間(1日に4.5時間)使用
              <br />
              した場合の目安電気料金※
            </div>
            <div
              style={{
                padding: '2px 6px',
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'flex-end',
                justifyContent: 'center',
                whiteSpace: 'nowrap',
              }}
            >
              <div style={{ display: 'inline-flex', alignItems: 'baseline', lineHeight: 1.05 }}>
                <span style={{ fontSize: 22, fontWeight: 900 }}>
                  {specs.annual_elec_bill_yen || '3,483'}
                </span>
                <span style={{ fontSize: 12.5, fontWeight: 800, marginLeft: 1 }}>円</span>
              </div>
              <div style={{ fontSize: 7.5, color: '#444' }}>※27円/kWh（税込）</div>
            </div>
          </div>

          {/* TV Body Dimensions Silhouette SVG */}
          <div style={{ background: '#FFFFFF', border: '1px solid #B5B5B5', flex: 1 }}>
            <div style={cellHeaderStyle}>本体サイズ</div>
            <div style={{ padding: '4px 6px' }}>
              <svg viewBox="0 0 220 135" style={{ width: '100%', height: 135, display: 'block' }}>
                <text x="4" y="12" fontSize="9.5" fontWeight="800" fill="#111">
                  高さ
                </text>
                <text x="4" y="23" fontSize="10" fontWeight="900" fill="#111">
                  {specs.height_cm || '64.5'}cm
                </text>

                <text x="95" y="22" textAnchor="middle" fontSize="10" fontWeight="900" fill="#111">
                  幅{specs.width_cm || '111.5'}cm
                </text>

                <text x="172" y="12" fontSize="9.5" fontWeight="800" fill="#111">
                  奥行
                </text>
                <text x="172" y="23" fontSize="10" fontWeight="900" fill="#111">
                  {specs.depth_cm || '5.7'}cm
                </text>

                {/* TV Front Screen */}
                <rect
                  x="48"
                  y="30"
                  width="96"
                  height="56"
                  fill="#B5B7B9"
                  stroke="#333333"
                  strokeWidth="2"
                />
                {/* TV Stand */}
                <polygon points="88,86 104,86 116,92 76,92" fill="#444444" />

                {/* Side Profile TV */}
                <rect x="164" y="30" width="6" height="56" fill="#444444" />
                <polygon points="156,92 178,92 172,86 162,86" fill="#444444" />

                {/* Dimension guide lines */}
                <line x1="34" y1="30" x2="46" y2="30" stroke="#777" strokeWidth="0.8" />
                <line x1="34" y1="86" x2="46" y2="86" stroke="#777" strokeWidth="0.8" />
                <line x1="40" y1="30" x2="40" y2="86" stroke="#777" strokeWidth="0.8" />

                <line x1="24" y1="30" x2="34" y2="30" stroke="#777" strokeWidth="0.8" />
                <line x1="24" y1="92" x2="74" y2="92" stroke="#777" strokeWidth="0.8" />
                <line x1="28" y1="30" x2="28" y2="92" stroke="#777" strokeWidth="0.8" />

                {/* Bottom texts */}
                <text x="4" y="96" fontSize="9" fontWeight="800" fill="#111">
                  高さ
                </text>
                <text x="4" y="106" fontSize="9.5" fontWeight="900" fill="#111">
                  {specs.height_stand_cm || '67.5'}cm
                </text>
                <text x="4" y="116" fontSize="7.5" fontWeight="700" fill="#111">
                  (スタンド取付時)
                </text>

                <text x="96" y="106" textAnchor="middle" fontSize="9.5" fontWeight="900" fill="#111">
                  幅{specs.width_stand_cm || '40.8'}cm
                </text>
                <text x="96" y="115" textAnchor="middle" fontSize="7.5" fontWeight="700" fill="#111">
                  (スタンド)
                </text>

                <text x="172" y="106" textAnchor="middle" fontSize="9.5" fontWeight="900" fill="#111">
                  奥行{specs.depth_stand_cm || '24.8'}cm
                </text>
                <text x="172" y="115" textAnchor="middle" fontSize="7.5" fontWeight="700" fill="#111">
                  (スタンド取付時)
                </text>

                <text x="142" y="131" textAnchor="middle" fontSize="10" fontWeight="900" fill="#111">
                  重さ{specs.weight_kg || '16.5'}kg
                  <tspan fontSize="8" fontWeight="700">
                    (スタンド取付時)
                  </tspan>
                </text>
              </svg>
            </div>
          </div>

          {/* Input Terminals 2x2 */}
          <div
            style={{
              background: '#FFFFFF',
              border: '1px solid #B5B5B5',
              display: 'grid',
              gridTemplateColumns: '20px 1fr',
            }}
          >
            <div
              style={{
                background: '#666666',
                color: '#FFFFFF',
                fontWeight: 700,
                fontSize: 10.5,
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
                lineHeight: 1.1,
              }}
            >
              <span>入</span>
              <span>力</span>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '0.92fr 1.08fr', fontSize: 9.5 }}>
              <div
                style={{
                  borderRight: '1px solid #CCC',
                  borderBottom: '1px solid #CCC',
                  padding: '3px 5px',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  fontWeight: 700,
                  whiteSpace: 'nowrap',
                }}
              >
                <span style={{ fontSize: 9 }}>HDMI入力</span>
                <span style={{ fontSize: 14, fontWeight: 900 }}>{specs.input_hdmi ?? 4}</span>
              </div>
              <div
                style={{
                  borderBottom: '1px solid #CCC',
                  padding: '3px 5px',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  fontWeight: 700,
                  whiteSpace: 'nowrap',
                }}
              >
                <span style={{ fontSize: 8 }}>アナログ音声入力</span>
                <span style={{ fontSize: 14, fontWeight: 900 }}>
                  {specs.input_analog_audio ?? 0}
                </span>
              </div>
              <div
                style={{
                  borderRight: '1px solid #CCC',
                  padding: '3px 5px',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  fontWeight: 700,
                  whiteSpace: 'nowrap',
                }}
              >
                <span style={{ fontSize: 9 }}>映像入力</span>
                <span style={{ fontSize: 14, fontWeight: 900 }}>{specs.input_video ?? 0}</span>
              </div>
              <div
                style={{
                  padding: '3px 5px',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  gap: 3,
                  fontWeight: 700,
                  whiteSpace: 'nowrap',
                  overflow: 'hidden',
                }}
              >
                <span style={{ fontSize: 9, flexShrink: 0 }}>USB</span>
                <span style={{ fontSize: 8.5, fontWeight: 900, whiteSpace: 'nowrap' }}>
                  {specs.input_usb || '2(うち録画用1)'}
                </span>
              </div>
            </div>
          </div>

          {/* Audio Output */}
          <div style={{ background: '#FFFFFF', border: '1px solid #B5B5B5' }}>
            <div style={cellHeaderStyle}>音声実用最大出力</div>
            <div
              style={{
                height: 26,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: fitFontSize(specs.audio_output || '40W', 13, 18, 9),
                fontWeight: 900,
                whiteSpace: 'nowrap',
              }}
            >
              {specs.audio_output || '40W'}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
