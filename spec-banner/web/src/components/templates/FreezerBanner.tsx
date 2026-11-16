import React from 'react';
import { DoorDiagram3DWithDimensions } from './DoorDiagram3D';
import {
  DoorSwingDiagramSvg,
  EAngleSelectPanel,
  JanBarcodeSvg,
  RecyclingFooterBar,
  UnifiedEnergyLabelBox,
} from './SharedBannerParts';

export const FreezerBanner: React.FC<{ specs: Record<string, any> }> = ({ specs }) => {
  const compartments = [1, 2, 3, 4, 5, 6].map((idx) => ({
    name: specs[`comp${idx}_name`] || '',
    capacity: specs[`comp${idx}_capacity_l`] || '',
    foodSpace: specs[`comp${idx}_food_space_l`] || '',
    badge:
      specs[`comp${idx}_badge`] ||
      (idx <= 2 && specs[`comp${idx}_name`] && String(specs[`comp${idx}_name`]).trim() !== '-'
        ? '霜取り不要'
        : ''),
  }));

  const hasEAngle = Boolean(
    (specs.base_model_no && String(specs.base_model_no).trim() !== '') ||
      (specs.original_point_1 && String(specs.original_point_1).trim() !== '')
  );

  const renderFlagCell = (val: any) => {
    const isOk = ['○', '〇', '◯', 'O', '1', 'true'].includes(String(val || '×').trim());
    return (
      <div
        style={{
          height: 30,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontSize: 22,
          fontWeight: 700,
        }}
      >
        {isOk ? '◯' : '×'}
      </div>
    );
  };

  return (
    <div
      style={{
        width: 552,
        background: '#FFFFFF',
        border: '1.5px solid #444444',
        padding: 12,
        fontFamily: "'BIZ UDPGothic', sans-serif",
        color: '#111111',
        boxSizing: 'border-box',
        display: 'flex',
        flexDirection: 'column',
        gap: 8,
        userSelect: 'none',
        overflow: 'hidden',
      }}
    >
      {/* Top Blue Header (#1C549D) */}
      <div
        style={{
          background: '#1C549D',
          color: '#FFFFFF',
          textAlign: 'center',
          fontWeight: 900,
          fontSize: 27,
          letterSpacing: '0.18em',
          padding: '4px 0',
          lineHeight: 1.2,
          whiteSpace: 'nowrap',
        }}
      >
        冷凍庫
      </div>

      {/* Maker Logo + Model + Capacity Row */}
      <div
        style={{
          display: 'flex',
          alignItems: 'flex-end',
          justifyContent: 'space-between',
          padding: '0 4px',
          whiteSpace: 'nowrap',
        }}
      >
        <div>
          <div
            style={{
              fontSize: String(specs.maker || '').length > 10 ? 15 : 26,
              fontWeight: 900,
              letterSpacing: '0.04em',
              lineHeight: 1.05,
            }}
          >
            {specs.maker || 'AQUA'}
          </div>
          <div style={{ fontSize: 12, fontWeight: 800, marginTop: 3 }}>
            {specs.model_no || 'AQFSF11R'}
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 4 }}>
            <span style={{ fontSize: 13, fontWeight: 800 }}>定格内容量</span>
            <span style={{ fontSize: 52, fontWeight: 800, lineHeight: 0.9 }}>
              {specs.capacity_l ?? 105}
            </span>
            <span style={{ fontSize: 26, fontWeight: 700 }}>L</span>
          </div>

          <div
            style={{
              borderLeft: '1.5px solid #666666',
              paddingLeft: 10,
              textAlign: 'center',
            }}
          >
            <div style={{ fontSize: 9.5, fontWeight: 800 }}>〈食品収納スペース〉</div>
            <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'center' }}>
              <span style={{ fontSize: 42, fontWeight: 800, lineHeight: 0.95 }}>
                {specs.food_space_l ?? 72}
              </span>
              <span style={{ fontSize: 22, fontWeight: 700, marginLeft: 2 }}>L</span>
            </div>
          </div>
        </div>
      </div>

      {/* Gray Main Diagram Box */}
      <div
        style={{
          background: '#E5E4E2',
          padding: '10px 10px 6px',
          display: 'flex',
          flexDirection: 'column',
          gap: 6,
        }}
      >
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: '226px 1fr',
            gap: 8,
          }}
        >
          {/* Left: 3D Freezer Door Layout + Dimensions */}
          <DoorDiagram3DWithDimensions
            doorLayout={String(specs.door_layout || '扉1枚B')}
            compartments={compartments}
            heightCm={specs.height_cm || '145.5'}
            widthCm={specs.width_cm || '36.0'}
            depthCm={specs.depth_cm || '63.5'}
            depthBodyOnlyCm={specs.depth_body_only_cm || '63.5'}
            showWidthBox={false}
            showFoodSpace={true}
            totalCapacityL={specs.capacity_l || 105}
          />

          {/* Right: Door Swing + Weight + Clearance + 4 Feature Flags */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6, minWidth: 0 }}>
            <DoorSwingDiagramSvg
              openType={String(specs.door_open_type || '右開き')}
              depthOpenCm={specs.depth_door_open_cm || '95.3'}
            />

            {/* Weight + Clearance Row */}
            <div style={{ display: 'grid', gridTemplateColumns: '84px 1fr', gap: 6 }}>
              <div
                style={{
                  background: '#FFFFFF',
                  border: '1px solid #666666',
                  display: 'flex',
                  flexDirection: 'column',
                  whiteSpace: 'nowrap',
                }}
              >
                <div
                  style={{
                    background: '#666666',
                    color: '#FFFFFF',
                    fontSize: 11,
                    fontWeight: 700,
                    textAlign: 'center',
                    padding: '2px 0',
                  }}
                >
                  本体質量
                </div>
                <div
                  style={{
                    flex: 1,
                    display: 'flex',
                    alignItems: 'baseline',
                    justifyContent: 'center',
                    padding: '4px 0',
                  }}
                >
                  <span style={{ fontSize: 23, fontWeight: 800 }}>{specs.weight_kg ?? 37}</span>
                  <span style={{ fontSize: 12.5, fontWeight: 700, marginLeft: 2 }}>kg</span>
                </div>
              </div>

              <div
                style={{
                  background: '#FFFFFF',
                  border: '1px solid #666666',
                  display: 'flex',
                  flexDirection: 'column',
                  whiteSpace: 'nowrap',
                }}
              >
                <div
                  style={{
                    background: '#666666',
                    color: '#FFFFFF',
                    fontSize: 11,
                    fontWeight: 700,
                    textAlign: 'center',
                    padding: '2px 0',
                  }}
                >
                  放熱スペース
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', flex: 1 }}>
                  <div style={{ borderRight: '1px solid #AAA', textAlign: 'center' }}>
                    <div
                      style={{
                        borderBottom: '1px solid #AAA',
                        fontSize: 9,
                        fontWeight: 700,
                      }}
                    >
                      左右
                    </div>
                    <div style={{ fontSize: 15.5, fontWeight: 800, paddingTop: 2 }}>
                      {specs.clearance_side_cm ?? 2}
                      <span style={{ fontSize: 9 }}>cm</span>
                    </div>
                  </div>
                  <div style={{ borderRight: '1px solid #AAA', textAlign: 'center' }}>
                    <div
                      style={{
                        borderBottom: '1px solid #AAA',
                        fontSize: 9,
                        fontWeight: 700,
                      }}
                    >
                      上
                    </div>
                    <div style={{ fontSize: 15.5, fontWeight: 800, paddingTop: 2 }}>
                      {specs.clearance_top_cm ?? 10}
                      <span style={{ fontSize: 9 }}>cm</span>
                    </div>
                  </div>
                  <div style={{ textAlign: 'center' }}>
                    <div
                      style={{
                        borderBottom: '1px solid #AAA',
                        fontSize: 9,
                        fontWeight: 700,
                      }}
                    >
                      背面
                    </div>
                    <div style={{ fontSize: 15.5, fontWeight: 800, paddingTop: 2 }}>
                      {specs.clearance_back_cm ?? 0}
                      <span style={{ fontSize: 9 }}>cm</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            {/* 4-Column Feature Grid */}
            <div
              style={{
                background: '#FFFFFF',
                border: '1px solid #666666',
                display: 'grid',
                gridTemplateColumns: '1fr 1fr 1fr 1.15fr',
                whiteSpace: 'nowrap',
              }}
            >
              <div style={{ borderRight: '1px solid #AAA' }}>
                <div
                  style={{
                    background: '#666666',
                    color: '#FFFFFF',
                    fontSize: 10,
                    fontWeight: 700,
                    height: 34,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    textAlign: 'center',
                    lineHeight: 1.15,
                  }}
                >
                  庫内
                  <br />
                  LED
                </div>
                {renderFlagCell(specs.feat_led)}
              </div>

              <div style={{ borderRight: '1px solid #AAA' }}>
                <div
                  style={{
                    background: '#666666',
                    color: '#FFFFFF',
                    fontSize: 10,
                    fontWeight: 700,
                    height: 34,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    textAlign: 'center',
                    lineHeight: 1.15,
                  }}
                >
                  急速
                  <br />
                  冷凍
                </div>
                {renderFlagCell(specs.feat_quick_freeze)}
              </div>

              <div style={{ borderRight: '1px solid #AAA' }}>
                <div
                  style={{
                    background: '#666666',
                    color: '#FFFFFF',
                    fontSize: 9.5,
                    fontWeight: 700,
                    height: 34,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    textAlign: 'center',
                    lineHeight: 1.15,
                  }}
                >
                  冷凍・冷蔵
                  <br />
                  切替
                </div>
                {renderFlagCell(specs.feat_mode_switch)}
              </div>

              <div>
                <div
                  style={{
                    background: '#666666',
                    color: '#FFFFFF',
                    fontSize: 8.5,
                    fontWeight: 700,
                    height: 34,
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'center',
                    justifyContent: 'center',
                    textAlign: 'center',
                    lineHeight: 1.1,
                  }}
                >
                  <span>耐熱</span>
                  <span>トップテーブル</span>
                  <span style={{ fontSize: 7.5 }}>(100℃)</span>
                </div>
                {renderFlagCell(specs.feat_heat_top)}
              </div>
            </div>
          </div>
        </div>

        <div style={{ fontSize: 7.5, color: '#222', whiteSpace: 'nowrap' }}>
          ※表記容積は、定格内容積、食品収納スペースの目安です。2015年JISで測定。 ※高さ・幅・奥行の単位はcm。
        </div>
      </div>

      {/* ■ Point Headline */}
      <div
        style={{
          display: 'flex',
          alignItems: 'baseline',
          gap: 8,
          padding: '2px 2px',
          whiteSpace: 'nowrap',
          overflow: 'hidden',
        }}
      >
        <span style={{ color: '#595757', fontSize: 15, fontWeight: 800, flexShrink: 0 }}>
          ■ Point
        </span>
        <span style={{ fontSize: 19, fontWeight: 900, color: '#111111' }}>
          {specs.point_text || '横幅36cmのスリムタイプ'}
        </span>
      </div>

      {/* Energy Label + Color Barcodes + Optional e angle Select */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: hasEAngle ? '210px 136px 1fr' : '216px 1fr',
          gap: 8,
          alignItems: 'stretch',
        }}
      >
        <UnifiedEnergyLabelBox
          star={specs.energy_star || '2.1'}
          targetYear={specs.energy_target_year || '2021年度'}
          achievementPct={specs.energy_achievement_pct || '114'}
          annualKwh={specs.annual_power_kwh || '320'}
          annualBillYen={specs.annual_elec_bill_yen || '8,640'}
        />

        {/* Barcodes Area */}
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            justifyContent: 'space-between',
            padding: '4px 2px',
            minWidth: 0,
            overflow: 'hidden',
          }}
        >
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {/* Primary Color + Barcode */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, minWidth: 0 }}>
              <div
                style={{
                  width: 14,
                  height: 40,
                  background: '#F4F4F4',
                  border: '1px solid #CCCCCC',
                  flexShrink: 0,
                }}
              />
              <div style={{ minWidth: 0, flex: 1, overflow: 'hidden' }}>
                <div
                  style={{
                    fontSize: 8.5,
                    fontWeight: 700,
                    lineHeight: 1.2,
                    whiteSpace: 'nowrap',
                  }}
                >
                  {specs.color_name || '(W) ホワイト'}
                </div>
                <JanBarcodeSvg
                  jan={String(specs.jan_code || '4582678514172')}
                  width={1.0}
                  height={22}
                />
              </div>
            </div>

            {/* Sub Color + Barcode if set */}
            {specs.sub_jan_code && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, minWidth: 0 }}>
                <div
                  style={{
                    width: 14,
                    height: 40,
                    background: '#1A1A1A',
                    border: '1px solid #333333',
                    flexShrink: 0,
                  }}
                />
                <div style={{ minWidth: 0, flex: 1, overflow: 'hidden' }}>
                  <div
                    style={{
                      fontSize: 8.5,
                      fontWeight: 700,
                      lineHeight: 1.2,
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {specs.sub_color_name || '(K) シャインブラック'}
                  </div>
                  <JanBarcodeSvg jan={String(specs.sub_jan_code)} width={1.0} height={22} />
                </div>
              </div>
            )}
          </div>

          <div style={{ fontSize: 7.5, color: '#333', marginTop: 2, whiteSpace: 'nowrap' }}>
            ※実際の色とは異なる場合がございます。
          </div>
        </div>

        {hasEAngle && (
          <EAngleSelectPanel
            modelNo={String(specs.model_no || '')}
            baseModelNo={String(specs.base_model_no || '')}
            point1={String(specs.original_point_1 || '')}
            point2={String(specs.original_point_2 || '')}
            point3={String(specs.original_point_3 || '')}
            makerName={String(specs.maker || '')}
            compact={true}
          />
        )}
      </div>

      {/* Bottom Recycling Fee Footer */}
      <RecyclingFooterBar />
    </div>
  );
};
