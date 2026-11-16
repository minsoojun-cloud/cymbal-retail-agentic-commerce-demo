import React, { useEffect, useRef } from 'react';
import JsBarcode from 'jsbarcode';

/**
 * Renders a crisp SVG barcode using JsBarcode (CODE128) constrained cleanly inside its container.
 */
export const JanBarcodeSvg: React.FC<{
  jan: string;
  width?: number;
  height?: number;
}> = ({ jan, width = 1.2, height = 24 }) => {
  const svgRef = useRef<SVGSVGElement | null>(null);

  useEffect(() => {
    if (!svgRef.current) return;
    const clean = (jan || '4900000000000').replace(/[^0-9A-Za-z]/g, '') || '4900000000000';
    try {
      JsBarcode(svgRef.current, clean, {
        format: 'CODE128',
        width,
        height,
        displayValue: true,
        fontSize: 10,
        fontOptions: 'bold',
        margin: 0,
        textMargin: 1,
        background: 'transparent',
        lineColor: '#111111',
      });
    } catch {
      // Fallback ignored
    }
  }, [jan, width, height]);

  return (
    <svg
      ref={svgRef}
      style={{
        width: '100%',
        maxWidth: '100%',
        height: 'auto',
        maxHeight: height + 14,
        display: 'block',
      }}
    />
  );
};

/**
 * Renders 5-star rating with partial/full gold stars matching Japan's unified energy label.
 * Uses pure SVG path clipping (no duplicate linearGradient IDs) so it never breaks in JPEG/PDF export.
 */
export const StarRatingRow: React.FC<{
  rating: string | number;
  size?: number;
}> = ({ rating, size = 14 }) => {
  const parsed = parseFloat(String(rating ?? '3.0'));
  const num = Number.isNaN(parsed) ? 3.0 : Math.max(0, Math.min(5, parsed));
  const stars = [1, 2, 3, 4, 5];
  const starPoints = '12,2 15.1,8.3 22,9.3 17,14.1 18.2,21 12,17.7 5.8,21 7,14.1 2,9.3 8.9,8.3';

  return (
    <div
      style={{
        display: 'inline-flex',
        gap: 1.5,
        alignItems: 'center',
        justifyContent: 'center',
        flexShrink: 0,
        whiteSpace: 'nowrap',
      }}
    >
      {stars.map((s) => {
        const diff = num - (s - 1);
        const fillRatio = diff >= 0.85 ? 1 : diff >= 0.25 ? 0.5 : 0;
        return (
          <svg
            key={s}
            width={size}
            height={size}
            viewBox="0 0 24 24"
            style={{ display: 'block', flexShrink: 0 }}
          >
            {/* Base white star */}
            <polygon
              points={starPoints}
              fill={fillRatio === 1 ? '#F5A623' : '#FFFFFF'}
              stroke="#555555"
              strokeWidth="1.4"
              strokeLinejoin="round"
            />
            {/* Half gold star overlay using left-half polygon */}
            {fillRatio === 0.5 && (
              <polygon
                points="12,2 12,17.7 5.8,21 7,14.1 2,9.3 8.9,8.3"
                fill="#F5A623"
                stroke="#555555"
                strokeWidth="1.0"
                strokeLinejoin="round"
              />
            )}
            {/* Re-stroke outline for crisp border */}
            <polygon
              points={starPoints}
              fill="none"
              stroke="#555555"
              strokeWidth="1.4"
              strokeLinejoin="round"
            />
          </svg>
        );
      })}
    </div>
  );
};

/**
 * Green unified Energy Label (省エネ性能) used in Freezer & Refrigerator banners.
 * Strictly bounded so inner tables/numbers never overflow or overlap adjacent barcodes.
 */
export const UnifiedEnergyLabelBox: React.FC<{
  star: string | number;
  targetYear: string | number;
  achievementPct: string | number;
  annualKwh: string | number;
  annualBillYen: string | number;
}> = ({ star, targetYear, achievementPct, annualKwh, annualBillYen }) => {
  const yearStr = String(targetYear || '2021年度').includes('年度')
    ? String(targetYear)
    : `${targetYear}年度`;

  const formattedStar = (() => {
    const n = parseFloat(String(star || '3.0'));
    return Number.isNaN(n) ? String(star || '3.0') : n.toFixed(1);
  })();

  return (
    <div
      style={{
        border: '3.5px solid #009B4C',
        borderRadius: 4,
        background: '#009B4C',
        display: 'grid',
        gridTemplateColumns: '74px minmax(0, 1fr)',
        gap: 3,
        padding: 3,
        color: '#FFFFFF',
        fontFamily: "'BIZ UDPGothic', sans-serif",
        boxSizing: 'border-box',
        width: '100%',
        overflow: 'hidden',
      }}
    >
      {/* Left white box: 省エネ性能 + rating number + 5 stars */}
      <div
        style={{
          background: '#FFFFFF',
          color: '#111111',
          padding: '5px 2px',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'space-between',
          boxSizing: 'border-box',
          minWidth: 0,
          overflow: 'hidden',
        }}
      >
        <div
          style={{
            color: '#009B4C',
            fontWeight: 900,
            fontSize: 12,
            letterSpacing: '0',
            whiteSpace: 'nowrap',
            lineHeight: 1.1,
          }}
        >
          省エネ性能
        </div>
        <div
          style={{
            color: '#EA5514',
            fontWeight: 900,
            fontSize: 35,
            lineHeight: 1.0,
            margin: '3px 0',
            whiteSpace: 'nowrap',
          }}
        >
          {formattedStar}
        </div>
        <StarRatingRow rating={formattedStar} size={12} />
      </div>

      {/* Right green details */}
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'space-between',
          minWidth: 0,
          overflow: 'hidden',
        }}
      >
        {/* Top white mini table */}
        <div
          style={{
            background: '#FFFFFF',
            color: '#111111',
            display: 'grid',
            gridTemplateColumns: '32px 0.8fr 1.2fr',
            border: '1px solid #009B4C',
            textAlign: 'center',
            boxSizing: 'border-box',
            width: '100%',
            overflow: 'hidden',
          }}
        >
          {/* e mark + target year */}
          <div
            style={{
              padding: '2px 1px',
              borderRight: '1px solid #CCCCCC',
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              minWidth: 0,
            }}
          >
            <div
              style={{
                width: 14,
                height: 14,
                borderRadius: '50%',
                background: '#009B4C',
                color: '#FFFFFF',
                fontWeight: 900,
                fontSize: 10,
                lineHeight: '14px',
                textAlign: 'center',
                flexShrink: 0,
              }}
            >
              e
            </div>
            <div
              style={{
                fontSize: 5.5,
                fontWeight: 800,
                marginTop: 1,
                lineHeight: 1.05,
                whiteSpace: 'nowrap',
              }}
            >
              目標年度
              <br />
              {yearStr}
            </div>
          </div>

          {/* Achievement % */}
          <div
            style={{
              padding: '2px 1px',
              borderRight: '1px solid #CCCCCC',
              display: 'flex',
              flexDirection: 'column',
              justifyContent: 'space-between',
              minWidth: 0,
            }}
          >
            <div style={{ fontSize: 6, fontWeight: 800, lineHeight: 1.05, whiteSpace: 'nowrap' }}>
              省エネ基準
              <br />
              達成率
            </div>
            <div
              style={{
                fontSize: 11,
                fontWeight: 900,
                marginTop: 1,
                whiteSpace: 'nowrap',
                lineHeight: 1.05,
              }}
            >
              {achievementPct}
              <span style={{ fontSize: 6.5 }}>%</span>
            </div>
          </div>

          {/* Annual Power kWh/年 */}
          <div
            style={{
              padding: '2px 1px',
              display: 'flex',
              flexDirection: 'column',
              justifyContent: 'space-between',
              minWidth: 0,
            }}
          >
            <div style={{ fontSize: 6, fontWeight: 800, lineHeight: 1.05, whiteSpace: 'nowrap' }}>
              年間消費
              <br />
              電力量
            </div>
            <div
              style={{
                fontSize: 10,
                fontWeight: 900,
                marginTop: 1,
                whiteSpace: 'nowrap',
                lineHeight: 1.05,
              }}
            >
              {annualKwh}
              <span style={{ fontSize: 5.5 }}>kWh/年</span>
            </div>
          </div>
        </div>

        {/* Middle text */}
        <div
          style={{
            textAlign: 'center',
            fontWeight: 800,
            fontSize: 8.5,
            lineHeight: 1.18,
            padding: '2px 1px 1px',
            whiteSpace: 'nowrap',
          }}
        >
          1年間使用した場合の
          <br />
          目安電気料金
        </div>

        {/* Bill amount */}
        <div
          style={{
            borderTop: '1px solid rgba(255,255,255,0.65)',
            borderBottom: '1px solid rgba(255,255,255,0.65)',
            textAlign: 'center',
            padding: '2px 0',
            fontWeight: 900,
            fontSize: 20,
            lineHeight: 1.05,
            whiteSpace: 'nowrap',
          }}
        >
          {annualBillYen}
          <span style={{ fontSize: 11, marginLeft: 1 }}>円</span>
        </div>

        <div
          style={{
            fontSize: 6.3,
            textAlign: 'center',
            lineHeight: 1.12,
            paddingTop: 1,
            whiteSpace: 'nowrap',
          }}
        >
          目安電気料金は使用条件や電力会社
          <br />
          等により異なります
        </div>
      </div>
    </div>
  );
};

/**
 * Top-down Door Swing Diagram SVG (`右開き` / `左開き` / `フレンチドア`).
 */
export const DoorSwingDiagramSvg: React.FC<{
  openType: string;
  depthOpenCm: string | number;
}> = ({ openType, depthOpenCm }) => {
  const isFrench = (openType || '').includes('フレンチ') || (openType || '').includes('両開き');
  const isLeft = (openType || '').includes('左開き') && !(openType || '').startsWith('右開き');
  const label = isFrench ? 'フレンチドア' : isLeft ? '左開き' : '右開き';

  return (
    <div
      style={{
        border: '1.5px solid #666666',
        background: '#FFFFFF',
        display: 'flex',
        flexDirection: 'column',
        boxSizing: 'border-box',
      }}
    >
      <div
        style={{
          background: '#666666',
          color: '#FFFFFF',
          fontWeight: 700,
          fontSize: 12,
          textAlign: 'center',
          padding: '2px 0',
          whiteSpace: 'nowrap',
        }}
      >
        扉開閉
      </div>
      <div
        style={{
          padding: '5px 8px',
          flex: 1,
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'space-between',
        }}
      >
        <svg viewBox="0 0 230 92" style={{ width: '100%', height: 82, display: 'block' }}>
          {isFrench ? (
            <>
              <rect x="20" y="6" width="84" height="36" fill="#FFFFFF" stroke="#444" strokeWidth="1.8" />
              <line x1="20" y1="42" x2="104" y2="42" stroke="#444" strokeWidth="2.5" />
              <line x1="20" y1="42" x2="4" y2="62" stroke="#444" strokeWidth="2" />
              <path d="M 62 42 A 42 42 0 0 1 4 62" fill="none" stroke="#444" strokeWidth="1.2" />
              <path d="M 46 48 Q 34 65 16 58" fill="none" stroke="#222" strokeWidth="2.6" />
              <polygon points="16,58 23,55 21,63" fill="#222" />
              <line x1="104" y1="42" x2="122" y2="62" stroke="#444" strokeWidth="2" />
              <path d="M 62 42 A 42 42 0 0 0 122 62" fill="none" stroke="#444" strokeWidth="1.2" />
              <path d="M 78 48 Q 90 65 108 58" fill="none" stroke="#222" strokeWidth="2.6" />
              <polygon points="108,58 101,55 103,63" fill="#222" />
            </>
          ) : isLeft ? (
            <>
              <rect x="36" y="6" width="60" height="36" fill="#FFFFFF" stroke="#444" strokeWidth="1.8" />
              <line x1="36" y1="42" x2="12" y2="68" stroke="#444" strokeWidth="2.2" />
              <path d="M 96 42 A 60 60 0 0 1 12 68" fill="none" stroke="#444" strokeWidth="1.2" />
              <path d="M 78 48 Q 55 72 28 62" fill="none" stroke="#222" strokeWidth="3" />
              <polygon points="28,62 36,59 34,67" fill="#222" />
            </>
          ) : (
            <>
              <rect x="28" y="6" width="54" height="36" fill="#FFFFFF" stroke="#444" strokeWidth="1.8" />
              <line x1="82" y1="42" x2="122" y2="66" stroke="#444" strokeWidth="2.2" />
              <path d="M 28 42 A 60 60 0 0 0 122 66" fill="none" stroke="#444" strokeWidth="1.2" />
              <path d="M 52 47 Q 72 74 100 66" fill="none" stroke="#222" strokeWidth="3" />
              <polygon points="100,66 92,63 94,71" fill="#222" />
            </>
          )}

          <line x1="90" y1="6" x2="195" y2="6" stroke="#444" strokeWidth="1" />
          <line x1="74" y1="84" x2="195" y2="84" stroke="#444" strokeWidth="1" />
          <line x1="176" y1="22" x2="176" y2="8" stroke="#111" strokeWidth="2" />
          <polygon points="176,6 172,14 180,14" fill="#111" />
          <line x1="176" y1="64" x2="176" y2="82" stroke="#111" strokeWidth="2" />
          <polygon points="176,84 172,76 180,76" fill="#111" />

          <text x="168" y="34" textAnchor="middle" fontSize="9.5" fontWeight="700" fill="#111">
            ドア全開時の奥行き
          </text>
          <text x="168" y="56" textAnchor="middle" fontSize="20" fontWeight="900" fill="#111">
            {depthOpenCm}
            <tspan fontSize="11" fontWeight="700">
              cm
            </tspan>
          </text>
        </svg>

        <div
          style={{
            background: '#666666',
            color: '#FFFFFF',
            fontWeight: 700,
            fontSize: 15,
            textAlign: 'center',
            padding: '2px 0',
            marginTop: 2,
            whiteSpace: 'nowrap',
          }}
        >
          {label}
        </div>
      </div>
    </div>
  );
};

/**
 * Orange `Cymbal Retail Cymbal オリジナルポイント` panel used in PC, Freezer, and Refrigerator banners.
 */
export const EAngleSelectPanel: React.FC<{
  modelNo: string;
  baseModelNo: string;
  headline?: string;
  point1?: string;
  point2?: string;
  point3?: string;
  makerName?: string;
  compact?: boolean;
}> = ({
  modelNo,
  baseModelNo,
  headline = '買った後も安心',
  point1,
  point2,
  point3,
  makerName,
  compact = false,
}) => {
  const points = [point1, point2, point3].filter((p) => p && String(p).trim() !== '');
  return (
    <div
      style={{
        border: '2px solid #F39800',
        background: '#F59E0B',
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'space-between',
        fontFamily: "'BIZ UDPGothic', sans-serif",
        height: '100%',
        boxSizing: 'border-box',
        overflow: 'hidden',
      }}
    >
      {/* Top White Logo Header */}
      <div
        style={{
          background: '#FFFFFF',
          padding: compact ? '5px 6px' : '10px 8px',
          textAlign: 'center',
        }}
      >
        <div
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 5,
            fontWeight: 900,
            fontSize: compact ? 16 : 22,
            color: '#1a73e8',
            letterSpacing: '0.02em',
            whiteSpace: 'nowrap',
          }}
        >
          <span>Cymbal</span>
          <span
            style={{
              background: '#1a73e8',
              color: '#FFFFFF',
              fontSize: compact ? 9 : 11,
              padding: '1px 5px',
              borderRadius: 3,
            }}
          >
            Retail
          </span>
        </div>
      </div>

      {/* Orange Title */}
      <div
        style={{
          color: '#FFFFFF',
          fontWeight: 900,
          fontSize: compact ? 13.5 : 20,
          textAlign: 'center',
          lineHeight: 1.2,
          padding: compact ? '3px 4px' : '6px 6px',
          whiteSpace: 'nowrap',
        }}
      >
        Cymbal
        <br />
        オリジナルポイント
      </div>

      {/* Inner White Card */}
      <div
        style={{
          background: '#FFFFFF',
          margin: compact ? '0 5px 4px' : '0 8px 6px',
          borderRadius: 7,
          overflow: 'hidden',
          flex: 1,
          display: 'flex',
          flexDirection: 'column',
          border: '1px solid #E5E7EB',
        }}
      >
        {/* Gray Base Model Strip */}
        <div
          style={{
            background: '#808285',
            color: '#FFFFFF',
            padding: compact ? '4px 5px' : '6px 8px',
            display: 'flex',
            alignItems: 'center',
            gap: 5,
          }}
        >
          <div
            style={{
              background: '#FFFFFF',
              color: '#111111',
              borderRadius: '50%',
              width: compact ? 38 : 50,
              height: compact ? 38 : 50,
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              fontWeight: 900,
              fontSize: compact ? 9.5 : 12,
              lineHeight: 1.1,
              border: '2px solid #EA5514',
              flexShrink: 0,
              whiteSpace: 'nowrap',
            }}
          >
            <span>ココが</span>
            <span>違う!</span>
          </div>
          <div style={{ fontSize: compact ? 8.5 : 10.5, lineHeight: 1.2, overflow: 'hidden' }}>
            <div style={{ fontWeight: 800, fontSize: compact ? 9.5 : 12, whiteSpace: 'nowrap' }}>
              {modelNo}
            </div>
            {baseModelNo && (
              <div style={{ opacity: 0.95, whiteSpace: 'nowrap' }}>
                ベースモデル
                <br />
                {baseModelNo}
              </div>
            )}
          </div>
        </div>

        {/* Points Callout Area */}
        <div
          style={{
            flex: 1,
            padding: compact ? '5px 6px' : '10px 10px',
            display: 'flex',
            flexDirection: 'column',
            justifyContent: 'center',
            alignItems: 'center',
            gap: compact ? 3 : 6,
            textAlign: 'center',
          }}
        >
          {headline && !compact && (
            <div style={{ color: '#EA5514', fontWeight: 900, fontSize: 19, lineHeight: 1.2 }}>
              {headline}
            </div>
          )}
          {points.map((pt, idx) => (
            <div
              key={idx}
              style={{
                background: idx === 0 && !compact ? '#EA5514' : 'transparent',
                color: idx === 0 && !compact ? '#FFFFFF' : '#EA5514',
                borderBottom: compact && idx < points.length - 1 ? '1px dashed #F39800' : 'none',
                padding: idx === 0 && !compact ? '6px 8px' : '2px 2px',
                borderRadius: idx === 0 && !compact ? 4 : 0,
                fontWeight: 900,
                fontSize: compact ? 10.5 : 17,
                lineHeight: 1.2,
                width: '100%',
                boxSizing: 'border-box',
              }}
            >
              {pt}
            </div>
          ))}
        </div>
      </div>

      {/* Bottom Maker & Model caption */}
      <div
        style={{
          fontSize: compact ? 7.5 : 10,
          color: '#111111',
          textAlign: 'right',
          padding: compact ? '0 6px 3px' : '0 10px 5px',
          fontWeight: 700,
          whiteSpace: 'nowrap',
        }}
      >
        {makerName} {modelNo}
      </div>
    </div>
  );
};

/**
 * Standard Recycling Fee Footer (`リサイクル料金・収集運搬費`) used at the bottom of Freezer & Refrigerator banners.
 */
export const RecyclingFooterBar: React.FC<{ compact?: boolean }> = ({ compact = false }) => {
  return (
    <div
      style={{
        border: '1.5px solid #666666',
        background: '#FFFFFF',
        display: 'grid',
        gridTemplateColumns: compact ? '1fr' : '136px 1fr',
        fontFamily: "'BIZ UDPGothic', sans-serif",
        boxSizing: 'border-box',
        overflow: 'hidden',
      }}
    >
      <div
        style={{
          background: '#595757',
          color: '#FFFFFF',
          padding: compact ? '3px 4px' : '4px 4px',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          textAlign: 'center',
          fontWeight: 700,
          whiteSpace: 'nowrap',
        }}
      >
        <div style={{ fontSize: compact ? 10.5 : 11, lineHeight: 1.15 }}>
          リサイクル料金・収集運搬費
        </div>
        <div style={{ fontSize: 7.8, opacity: 0.92, marginTop: 1 }}>〈当店にて買い替えの場合〉</div>
      </div>

      <div
        style={{
          padding: compact ? '3px 3px' : '4px 6px',
          display: 'grid',
          gridTemplateColumns: '1fr auto 1fr',
          alignItems: 'center',
          gap: compact ? 2 : 4,
          minWidth: 0,
        }}
      >
        {/* Left: Recycling fee */}
        <div style={{ display: 'flex', alignItems: 'center', gap: compact ? 2 : 3, minWidth: 0 }}>
          <div
            style={{
              background: '#666666',
              color: '#FFFFFF',
              fontSize: compact ? 6.5 : 7.8,
              fontWeight: 700,
              padding: compact ? '2px 2px' : '3px 3px',
              lineHeight: 1.15,
              textAlign: 'center',
              whiteSpace: 'nowrap',
              flexShrink: 0,
            }}
          >
            リサイクル
            <br />
            料金
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: compact ? 2 : 3, flex: 1 }}>
            <div style={{ textAlign: 'center' }}>
              <div
                style={{
                  border: '1px solid #888',
                  fontSize: compact ? 6.5 : 7.5,
                  fontWeight: 700,
                  padding: '0 1px',
                  whiteSpace: 'nowrap',
                }}
              >
                170L以下
              </div>
              <div
                style={{
                  fontSize: compact ? 9.8 : 12,
                  fontWeight: 900,
                  marginTop: 1,
                  whiteSpace: 'nowrap',
                }}
              >
                3,740<span style={{ fontSize: compact ? 6 : 7.5 }}>円〜</span>
              </div>
            </div>
            <div style={{ textAlign: 'center' }}>
              <div
                style={{
                  border: '1px solid #888',
                  fontSize: compact ? 6.5 : 7.5,
                  fontWeight: 700,
                  padding: '0 1px',
                  whiteSpace: 'nowrap',
                }}
              >
                171L以上
              </div>
              <div
                style={{
                  fontSize: compact ? 9.8 : 12,
                  fontWeight: 900,
                  marginTop: 1,
                  whiteSpace: 'nowrap',
                }}
              >
                4,730<span style={{ fontSize: compact ? 6 : 7.5 }}>円〜</span>
              </div>
            </div>
          </div>
        </div>

        {/* Plus circle */}
        <div
          style={{
            width: compact ? 11 : 13,
            height: compact ? 11 : 13,
            borderRadius: '50%',
            background: '#444444',
            color: '#FFFFFF',
            fontSize: compact ? 8 : 9.5,
            fontWeight: 900,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            flexShrink: 0,
          }}
        >
          +
        </div>

        {/* Right: Transport fee */}
        <div style={{ display: 'flex', alignItems: 'center', gap: compact ? 2 : 3, minWidth: 0 }}>
          <div
            style={{
              background: '#666666',
              color: '#FFFFFF',
              fontSize: compact ? 6.5 : 7.8,
              fontWeight: 700,
              padding: compact ? '2px 2px' : '3px 3px',
              lineHeight: 1.15,
              textAlign: 'center',
              whiteSpace: 'nowrap',
              flexShrink: 0,
            }}
          >
            収集
            <br />
            運搬費
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: compact ? 2 : 3, flex: 1 }}>
            <div style={{ textAlign: 'center' }}>
              <div
                style={{
                  border: '1px solid #888',
                  fontSize: compact ? 6.5 : 7.5,
                  fontWeight: 700,
                  padding: '0 1px',
                  whiteSpace: 'nowrap',
                }}
              >
                250L以下
              </div>
              <div
                style={{
                  fontSize: compact ? 9.8 : 12,
                  fontWeight: 900,
                  marginTop: 1,
                  whiteSpace: 'nowrap',
                }}
              >
                1,100<span style={{ fontSize: compact ? 6 : 7.5 }}>円〜</span>
              </div>
            </div>
            <div style={{ textAlign: 'center' }}>
              <div
                style={{
                  border: '1px solid #888',
                  fontSize: compact ? 6.5 : 7.5,
                  fontWeight: 700,
                  padding: '0 1px',
                  whiteSpace: 'nowrap',
                }}
              >
                251L以上
              </div>
              <div
                style={{
                  fontSize: compact ? 9.8 : 12,
                  fontWeight: 900,
                  marginTop: 1,
                  whiteSpace: 'nowrap',
                }}
              >
                1,650<span style={{ fontSize: compact ? 6 : 7.5 }}>円〜</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
