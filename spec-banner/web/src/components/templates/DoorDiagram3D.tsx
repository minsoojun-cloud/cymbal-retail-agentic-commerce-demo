import React from 'react';

export interface CompartmentItem {
  name: string;
  capacity: string | number;
  foodSpace?: string | number;
  badge?: string;
}

/**
 * Metadata for all 12 official EDION 3D Door Layouts (`扉1枚A` .. `扉5枚C`)
 * extracted from the `画像` tab of `【メーカー様名】冷凍庫_機能表入力シート.xlsx` and `冷蔵庫_機能表入力シート.xlsx`.
 */
export const DOOR_LAYOUT_PRESETS: Record<
  string,
  {
    doorCount: number;
    roomCount: number;
    defaultRooms: Array<{ name: string; ratio: number }>;
    description: string;
  }
> = {
  扉1枚A: {
    doorCount: 1,
    roomCount: 1,
    defaultRooms: [{ name: '冷凍室', ratio: 1.0 }],
    description: '1ドア小型（キューブ型・1室）',
  },
  扉1枚B: {
    doorCount: 1,
    roomCount: 1,
    defaultRooms: [{ name: '冷凍室', ratio: 1.0 }],
    description: '1ドア縦型（トール型・1室）',
  },
  扉2枚A: {
    doorCount: 2,
    roomCount: 2,
    defaultRooms: [
      { name: '冷凍室', ratio: 0.45 },
      { name: '冷蔵室', ratio: 0.55 },
    ],
    description: '2ドア左右開き（サイドバイサイド・2室）',
  },
  扉2枚B: {
    doorCount: 2,
    roomCount: 2,
    defaultRooms: [
      { name: '冷凍室', ratio: 0.52 },
      { name: '冷凍室', ratio: 0.48 },
    ],
    description: '2ドア上下均等（上室50%・下室50%）',
  },
  扉2枚C: {
    doorCount: 2,
    roomCount: 2,
    defaultRooms: [
      { name: '冷凍室', ratio: 0.34 },
      { name: '冷蔵室', ratio: 0.66 },
    ],
    description: '2ドア上段小・下段大（上室34%・下室66%）',
  },
  扉2枚D: {
    doorCount: 2,
    roomCount: 2,
    defaultRooms: [
      { name: '冷蔵室', ratio: 0.65 },
      { name: '冷凍室', ratio: 0.35 },
    ],
    description: '2ドア上段大・下段小（上室65%・下室35%）',
  },
  扉3枚: {
    doorCount: 3,
    roomCount: 3,
    defaultRooms: [
      { name: '冷蔵室', ratio: 0.52 },
      { name: '野菜室', ratio: 0.24 },
      { name: '冷凍室', ratio: 0.24 },
    ],
    description: '3ドア（1室:上段大 / 2室:中段 / 3室:下段）',
  },
  扉4枚: {
    doorCount: 4,
    roomCount: 4,
    defaultRooms: [
      { name: '冷蔵室', ratio: 0.48 },
      { name: '切替室', ratio: 0.16 },
      { name: '冷凍室', ratio: 0.18 },
      { name: '野菜室', ratio: 0.18 },
    ],
    description: '4ドア4段（1室〜4室 縦4段）',
  },
  扉4枚2室: {
    doorCount: 4,
    roomCount: 2,
    defaultRooms: [
      { name: '冷蔵室', ratio: 0.60 },
      { name: '冷凍室', ratio: 0.40 },
    ],
    description: '4ドアフレンチ2室（中央縦分割＋上下2室）',
  },
  扉5枚A: {
    doorCount: 5,
    roomCount: 5,
    defaultRooms: [
      { name: '冷蔵室', ratio: 0.51 },
      { name: '野菜室', ratio: 0.20 },
      { name: '製氷室', ratio: 0.04 },
      { name: '冷凍室', ratio: 0.05 },
      { name: '冷凍室', ratio: 0.20 },
    ],
    description: '5ドアA（1室:上 / 2室:中 / 3・4室:左右分割 / 5室:下）',
  },
  扉5枚B: {
    doorCount: 5,
    roomCount: 5,
    defaultRooms: [
      { name: '冷蔵室', ratio: 0.51 },
      { name: '製氷室', ratio: 0.04 },
      { name: '冷凍室', ratio: 0.05 },
      { name: '冷凍室', ratio: 0.20 },
      { name: '野菜室', ratio: 0.20 },
    ],
    description: '5ドアB（1室:上 / 2・3室:左右分割 / 4室:中下 / 5室:下）',
  },
  扉5枚C: {
    doorCount: 5,
    roomCount: 5,
    defaultRooms: [
      { name: '冷蔵室', ratio: 0.48 },
      { name: '製氷室', ratio: 0.06 },
      { name: '切替室', ratio: 0.08 },
      { name: '冷凍室', ratio: 0.18 },
      { name: '野菜室', ratio: 0.20 },
    ],
    description: '5ドアC（1室:上 / 左2・3室上下＋右4室縦長 / 5室:下）',
  },
};

const CIRCLED_NUMS = ['①', '②', '③', '④', '⑤', '⑥'];

/**
 * Renders a crisp, vector-accurate 3D Refrigerator / Freezer illustration for all 12 layouts (`扉1枚A`..`扉5枚C`),
 * including curved door-seam dividers, 3D top/right perspective faces, compartment labels, and H/W/D dimensions.
 */
export const DoorDiagram3DWithDimensions: React.FC<{
  doorLayout: string;
  compartments: CompartmentItem[];
  heightCm: string | number;
  widthCm: string | number;
  depthCm: string | number;
  depthBodyOnlyCm?: string | number;
  showWidthBox?: boolean;
  showFoodSpace?: boolean;
  totalCapacityL?: string | number;
}> = ({
  doorLayout,
  compartments,
  heightCm,
  widthCm,
  depthCm,
  depthBodyOnlyCm,
  showWidthBox = false,
  showFoodSpace = false,
  totalCapacityL,
}) => {
  const layoutKey = DOOR_LAYOUT_PRESETS[doorLayout] ? doorLayout : '扉1枚B';
  const preset = DOOR_LAYOUT_PRESETS[layoutKey];
  const totalCapNum = parseFloat(String(totalCapacityL || '')) || 300;

  // Build resolved compartments for every slot required by `layoutKey`
  // so switching `doorLayout` ALWAYS updates the visual structure immediately!
  const getSlotItem = (slotIdx: number): CompartmentItem => {
    const raw = compartments[slotIdx];
    const hasName = raw && raw.name && String(raw.name).trim() !== '' && String(raw.name).trim() !== '-';
    const hasCap = raw && raw.capacity !== undefined && String(raw.capacity).trim() !== '';

    const fallbackDef = preset.defaultRooms[slotIdx] || { name: `${slotIdx + 1}室`, ratio: 0.2 };
    const name = hasName ? String(raw.name) : `${CIRCLED_NUMS[slotIdx] || ''}${fallbackDef.name}`;
    const capacity = hasCap
      ? raw.capacity
      : Math.max(10, Math.round(totalCapNum * fallbackDef.ratio));

    return {
      name,
      capacity,
      foodSpace: raw?.foodSpace,
      badge: raw?.badge,
    };
  };

  // Curved divider bar matching the subtle downward arc in EDION's specimen 3D illustrations
  const CurvedDivider: React.FC<{ height?: number }> = ({ height = 8 }) => (
    <svg
      viewBox="0 0 100 10"
      preserveAspectRatio="none"
      style={{ width: '100%', height, display: 'block', flexShrink: 0 }}
    >
      <rect x="0" y="0" width="100" height="10" fill="#595757" />
      <path d="M 0,0 Q 50,4.5 100,0" fill="#FFFFFF" />
      <path d="M 0,10 Q 50,13.5 100,10" fill="#595757" />
    </svg>
  );

  const renderSlotBox = (
    slotIdx: number,
    opts?: { compact?: boolean; veryCompact?: boolean; frenchSplitLine?: boolean }
  ) => {
    const item = getSlotItem(slotIdx);
    const compact = opts?.compact || false;
    const veryCompact = opts?.veryCompact || false;
    return (
      <div
        style={{
          position: 'relative',
          flex: 1,
          background: '#FFFFFF',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          textAlign: 'center',
          padding: veryCompact ? '1px 1px' : compact ? '2px 2px' : '3px 4px',
          lineHeight: 1.05,
          minWidth: 0,
          minHeight: 0,
          overflow: 'hidden',
        }}
      >
        {/* Optional vertical French-door center line behind text (for 扉4枚2室) */}
        {opts?.frenchSplitLine && (
          <div
            style={{
              position: 'absolute',
              top: 0,
              bottom: 0,
              left: '50%',
              width: 3,
              transform: 'translateX(-50%)',
              background: '#595757',
              zIndex: 0,
            }}
          />
        )}

        <div
          style={{
            position: 'relative',
            zIndex: 1,
            background: opts?.frenchSplitLine ? 'rgba(255,255,255,0.92)' : 'transparent',
            padding: opts?.frenchSplitLine ? '2px 5px' : 0,
            borderRadius: 2,
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          <div
            style={{
              fontSize: veryCompact ? 8 : compact ? 9 : 11,
              fontWeight: 800,
              color: '#111111',
              whiteSpace: 'nowrap',
            }}
          >
            {item.name}
          </div>
          <div
            style={{
              fontSize: veryCompact ? 15 : compact ? 17.5 : 22,
              fontWeight: 900,
              color: '#111111',
              lineHeight: 1.05,
              whiteSpace: 'nowrap',
            }}
          >
            {item.capacity}
            <span style={{ fontSize: veryCompact ? 9.5 : compact ? 11 : 13.5 }}>L</span>
          </div>
          {showFoodSpace && item.foodSpace && (
            <div
              style={{
                fontSize: veryCompact ? 8 : 9.5,
                fontWeight: 700,
                color: '#222222',
                whiteSpace: 'nowrap',
              }}
            >
              〈{item.foodSpace}L〉
            </div>
          )}
          {item.badge && !veryCompact && (
            <div
              style={{
                background: '#595757',
                color: '#FFFFFF',
                fontSize: compact ? 8 : 9.5,
                fontWeight: 700,
                padding: '1px 6px',
                marginTop: 2,
                whiteSpace: 'nowrap',
              }}
            >
              {item.badge}
            </div>
          )}
        </div>
      </div>
    );
  };

  // Render the interior compartment layout matching the exact selected 3D layout key
  const renderFrontCompartments = () => {
    switch (layoutKey) {
      case '扉1枚A':
      case '扉1枚B':
        return <div style={{ flex: 1, display: 'flex' }}>{renderSlotBox(0)}</div>;

      case '扉2枚A':
        // Left-Right Side-by-Side 2 Doors
        return (
          <div
            style={{
              flex: 1,
              display: 'grid',
              gridTemplateColumns: '1fr 1fr',
              gap: 4,
              background: '#595757',
            }}
          >
            {renderSlotBox(0, { compact: true })}
            {renderSlotBox(1, { compact: true })}
          </div>
        );

      case '扉2枚B':
        // 50% Top / 50% Bottom
        return (
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: '#595757' }}>
            <div style={{ flex: 1, display: 'flex' }}>{renderSlotBox(0)}</div>
            <CurvedDivider height={7} />
            <div style={{ flex: 1, display: 'flex' }}>{renderSlotBox(1)}</div>
          </div>
        );

      case '扉2枚C':
        // 35% Small Top / 65% Large Bottom
        return (
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: '#595757' }}>
            <div style={{ flex: 0.54, display: 'flex' }}>{renderSlotBox(0, { compact: true })}</div>
            <CurvedDivider height={7} />
            <div style={{ flex: 1, display: 'flex' }}>{renderSlotBox(1)}</div>
          </div>
        );

      case '扉2枚D':
        // 65% Large Top / 35% Small Bottom
        return (
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: '#595757' }}>
            <div style={{ flex: 1, display: 'flex' }}>{renderSlotBox(0)}</div>
            <CurvedDivider height={7} />
            <div style={{ flex: 0.54, display: 'flex' }}>{renderSlotBox(1, { compact: true })}</div>
          </div>
        );

      case '扉3枚':
        // 3 Stacked Doors (Top Large, Middle Medium, Bottom Medium)
        return (
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: '#595757' }}>
            <div style={{ flex: 1.45, display: 'flex' }}>{renderSlotBox(0)}</div>
            <CurvedDivider height={6} />
            <div style={{ flex: 0.9, display: 'flex' }}>{renderSlotBox(1, { compact: true })}</div>
            <CurvedDivider height={6} />
            <div style={{ flex: 0.9, display: 'flex' }}>{renderSlotBox(2, { compact: true })}</div>
          </div>
        );

      case '扉4枚':
        // 4 Stacked Doors
        return (
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: '#595757' }}>
            <div style={{ flex: 1.4, display: 'flex' }}>{renderSlotBox(0, { compact: true })}</div>
            <CurvedDivider height={5} />
            <div style={{ flex: 0.72, display: 'flex' }}>
              {renderSlotBox(1, { veryCompact: true })}
            </div>
            <CurvedDivider height={5} />
            <div style={{ flex: 0.72, display: 'flex' }}>
              {renderSlotBox(2, { veryCompact: true })}
            </div>
            <CurvedDivider height={5} />
            <div style={{ flex: 0.72, display: 'flex' }}>
              {renderSlotBox(3, { veryCompact: true })}
            </div>
          </div>
        );

      case '扉4枚2室':
        // 4-Door French (2 compartments with center vertical split line)
        return (
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: '#595757' }}>
            <div style={{ flex: 1.25, display: 'flex' }}>
              {renderSlotBox(0, { frenchSplitLine: true })}
            </div>
            <CurvedDivider height={7} />
            <div style={{ flex: 1, display: 'flex' }}>
              {renderSlotBox(1, { frenchSplitLine: true })}
            </div>
          </div>
        );

      case '扉5枚A':
        // 1: Top, 2: Upper-Mid, 3|4: Lower-Mid Split, 5: Bottom
        return (
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: '#595757' }}>
            <div style={{ flex: 1.45, display: 'flex' }}>{renderSlotBox(0)}</div>
            <CurvedDivider height={5} />
            <div style={{ flex: 0.78, display: 'flex' }}>{renderSlotBox(1, { compact: true })}</div>
            <CurvedDivider height={5} />
            <div
              style={{
                flex: 0.82,
                display: 'grid',
                gridTemplateColumns: '0.92fr 1.08fr',
                gap: 4,
                background: '#595757',
              }}
            >
              {renderSlotBox(2, { veryCompact: true })}
              {renderSlotBox(3, { veryCompact: true })}
            </div>
            <CurvedDivider height={5} />
            <div style={{ flex: 0.85, display: 'flex' }}>{renderSlotBox(4, { compact: true })}</div>
          </div>
        );

      case '扉5枚B':
        // 1: Top, 2|3: Upper-Mid Split, 4: Lower-Mid, 5: Bottom
        return (
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: '#595757' }}>
            <div style={{ flex: 1.45, display: 'flex' }}>{renderSlotBox(0)}</div>
            <CurvedDivider height={5} />
            <div
              style={{
                flex: 0.82,
                display: 'grid',
                gridTemplateColumns: '0.92fr 1.08fr',
                gap: 4,
                background: '#595757',
              }}
            >
              {renderSlotBox(1, { veryCompact: true })}
              {renderSlotBox(2, { veryCompact: true })}
            </div>
            <CurvedDivider height={5} />
            <div style={{ flex: 0.78, display: 'flex' }}>{renderSlotBox(3, { compact: true })}</div>
            <CurvedDivider height={5} />
            <div style={{ flex: 0.85, display: 'flex' }}>{renderSlotBox(4, { compact: true })}</div>
          </div>
        );

      case '扉5枚C':
        // 1: Top, Middle: (2 top-left + 3 bottom-left) | (4 tall right), 5: Bottom
        return (
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: '#595757' }}>
            <div style={{ flex: 1.35, display: 'flex' }}>{renderSlotBox(0, { compact: true })}</div>
            <CurvedDivider height={5} />
            <div
              style={{
                flex: 1.45,
                display: 'grid',
                gridTemplateColumns: '0.92fr 1.08fr',
                gap: 4,
                background: '#595757',
              }}
            >
              <div
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 4,
                  background: '#595757',
                }}
              >
                <div style={{ flex: 1, display: 'flex' }}>
                  {renderSlotBox(1, { veryCompact: true })}
                </div>
                <div style={{ flex: 1, display: 'flex' }}>
                  {renderSlotBox(2, { veryCompact: true })}
                </div>
              </div>
              <div style={{ display: 'flex' }}>{renderSlotBox(3, { compact: true })}</div>
            </div>
            <CurvedDivider height={5} />
            <div style={{ flex: 0.82, display: 'flex' }}>{renderSlotBox(4, { compact: true })}</div>
          </div>
        );

      default:
        return <div style={{ flex: 1, display: 'flex' }}>{renderSlotBox(0)}</div>;
    }
  };

  // `扉1枚A` is a compact cube-style 1-door unit (shorter height than `扉1枚B`)
  const isCube1A = layoutKey === '扉1枚A';
  const boxHeight = isCube1A ? 172 : 246;

  return (
    <div
      style={{
        position: 'relative',
        display: 'flex',
        flexDirection: 'column',
        userSelect: 'none',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'flex-end', minHeight: 246 }}>
        {/* Pure Vector 3D Cabinet Perspective Wrapper + Front Door Compartments */}
        <div
          style={{
            position: 'relative',
            width: 142,
            height: boxHeight,
            flexShrink: 0,
          }}
        >
          {/* 3D Perspective Cabinet SVG (Top Bevel + Front Frame + Right Side Depth Face) */}
          <svg
            viewBox="0 0 142 246"
            preserveAspectRatio="none"
            style={{
              position: 'absolute',
              inset: 0,
              width: '100%',
              height: '100%',
              display: 'block',
            }}
          >
            {/* Top 3D Perspective Slant */}
            <polygon points="0,7 24,0 142,0 142,7" fill="#595757" />
            {/* Main Front & Side Body Block */}
            <polygon points="0,7 115,7 115,246 0,246" fill="#595757" />
            {/* Right Side 3D Depth Face */}
            <polygon points="115,7 142,0 142,238 115,246" fill="#595757" />
          </svg>

          {/* Front White Door Area */}
          <div
            style={{
              position: 'absolute',
              top: isCube1A ? '6%' : '4.2%',
              left: '4.5%',
              width: '74.5%',
              height: isCube1A ? '87%' : '90.5%',
              display: 'flex',
              flexDirection: 'column',
              background: '#595757',
              boxSizing: 'border-box',
              overflow: 'hidden',
            }}
          >
            {renderFrontCompartments()}
          </div>
        </div>

        {/* Right Side Vertical Height Arrow */}
        <div
          style={{
            width: 82,
            height: boxHeight,
            position: 'relative',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            flexShrink: 0,
          }}
        >
          <svg
            viewBox="0 0 82 246"
            preserveAspectRatio="none"
            style={{
              position: 'absolute',
              inset: 0,
              width: '100%',
              height: '100%',
            }}
          >
            <line x1="4" y1="4" x2="54" y2="4" stroke="#333" strokeWidth="1.2" />
            <line x1="4" y1="242" x2="54" y2="242" stroke="#333" strokeWidth="1.2" />
            <line x1="40" y1="92" x2="40" y2="6" stroke="#111" strokeWidth="1.6" />
            <polygon points="40,4 36,12 44,12" fill="#111" />
            <line x1="40" y1="152" x2="40" y2="240" stroke="#111" strokeWidth="1.6" />
            <polygon points="40,242 36,234 44,234" fill="#111" />
          </svg>
          <div
            style={{
              position: 'relative',
              zIndex: 1,
              textAlign: 'center',
              lineHeight: 1.1,
              whiteSpace: 'nowrap',
            }}
          >
            <div style={{ fontSize: 11.5, fontWeight: 800 }}>高さ</div>
            <div style={{ fontSize: 20, fontWeight: 900 }}>
              {heightCm}
              <span style={{ fontSize: 11 }}>cm</span>
            </div>
          </div>
        </div>
      </div>

      {/* Bottom Width & Depth Row */}
      <div
        style={{
          display: 'flex',
          alignItems: 'flex-start',
          marginTop: 3,
          gap: 4,
          whiteSpace: 'nowrap',
        }}
      >
        {showWidthBox ? (
          <div
            style={{
              border: '1.2px solid #444444',
              background: '#FFFFFF',
              display: 'inline-flex',
              alignItems: 'center',
              height: 27,
              flexShrink: 0,
            }}
          >
            <span
              style={{
                background: '#666666',
                color: '#FFFFFF',
                fontSize: 10,
                fontWeight: 700,
                padding: '0 4px',
                height: '100%',
                display: 'inline-flex',
                alignItems: 'center',
              }}
            >
              横幅
            </span>
            <span
              style={{
                padding: '0 5px',
                fontSize: 20,
                fontWeight: 900,
                lineHeight: 1,
              }}
            >
              {widthCm}
              <span style={{ fontSize: 10.5, fontWeight: 700 }}>cm</span>
            </span>
          </div>
        ) : (
          <div
            style={{
              width: 112,
              textAlign: 'center',
              borderLeft: '1px solid #333',
              borderRight: '1px solid #333',
              paddingTop: 2,
              flexShrink: 0,
            }}
          >
            <span style={{ fontSize: 10.5, fontWeight: 800 }}>←幅</span>
            <span style={{ fontSize: 19, fontWeight: 900 }}>{widthCm}</span>
            <span style={{ fontSize: 10.5, fontWeight: 800 }}>cm→</span>
          </div>
        )}

        {/* Depth info */}
        <div style={{ fontSize: 9.5, lineHeight: 1.15, paddingLeft: 2 }}>
          <div>
            <span style={{ fontWeight: 800, fontSize: 10.5 }}>奥行 </span>
            <span style={{ fontWeight: 900, fontSize: 18 }}>{depthCm}</span>
            <span style={{ fontWeight: 700, fontSize: 10 }}>cm</span>
          </div>
          {depthBodyOnlyCm && (
            <div style={{ fontSize: 7.2, fontWeight: 700, color: '#222' }}>
              (脚カバー・ハンドル除く 奥行{depthBodyOnlyCm}cm)
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
