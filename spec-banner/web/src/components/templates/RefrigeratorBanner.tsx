import React from 'react';
import { DoorDiagram3DWithDimensions } from './DoorDiagram3D';
import {
  DoorSwingDiagramSvg,
  EAngleSelectPanel,
  JanBarcodeSvg,
  RecyclingFooterBar,
  UnifiedEnergyLabelBox,
} from './SharedBannerParts';

export const RefrigeratorBanner: React.FC<{ specs: Record<string, any> }> = ({ specs }) => {
  const cap = Number(specs.capacity_l || 595);
  const isLarge = cap >= 350; // 350L以上 = Emerald Green (#009250), 349L以下 = Sky Blue (#29ABE2)
  const headerBg = isLarge ? '#009250' : '#29ABE2';

  const compartments = [1, 2, 3, 4, 5, 6].map((idx) => ({
    name: specs[`comp${idx}_name`] || '',
    capacity: specs[`comp${idx}_capacity_l`] || '',
    foodSpace: specs[`comp${idx}_food_space_l`] || '',
  }));

  const hasEAngle = Boolean(
    (specs.base_model_no && String(specs.base_model_no).trim() !== '') ||
      (specs.original_point_1 && String(specs.original_point_1).trim() !== '')
  );

  const isCircleOk = (val: any) =>
    ['○', '〇', '◯', 'O', '1', 'true'].includes(String(val || '×').trim());

  const renderFlagSymbol = (val: any, size = 24) => (
    <div
      style={{
        height: 34,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        fontSize: size,
        fontWeight: 700,
      }}
    >
      {isCircleOk(val) ? '◯' : '×'}
    </div>
  );

  const warrantyYears =
    String(specs.long_warranty || (isLarge ? '10年' : '5年')).replace(/[^0-9]/g, '') || '10';

  return (
    <div
      style={{
        width: 552,
        background: '#FFFFFF',
        border: '1.5px solid #333333',
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
      {/* Top Color Header (#29ABE2 for <=349L, #009250 for >=350L) */}
      <div
        style={{
          background: headerBg,
          color: '#FFFFFF',
          padding: '8px 16px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          whiteSpace: 'nowrap',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          {/* Circled 定格内容量 badge */}
          <div
            style={{
              width: 38,
              height: 38,
              borderRadius: '50%',
              border: '1.8px solid #FFFFFF',
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: 9.5,
              fontWeight: 800,
              lineHeight: 1.1,
              flexShrink: 0,
            }}
          >
            <span>定格</span>
            <span>内容量</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 4 }}>
            <span style={{ fontSize: 46, fontWeight: 900, lineHeight: 0.95 }}>{cap}L</span>
            <span style={{ fontSize: 28, fontWeight: 900 }}>冷蔵庫</span>
          </div>
        </div>

        <div style={{ textAlign: 'left', lineHeight: 1.15 }}>
          <div style={{ fontSize: 13, fontWeight: 900, letterSpacing: '0.04em' }}>
            {specs.maker || (isLarge ? 'TOSHIBA' : 'HITACHI')}
          </div>
          <div style={{ fontSize: 24, fontWeight: 900 }}>
            {specs.model_no || (isLarge ? 'GRA600XFS' : 'R27XN')}
          </div>
        </div>
      </div>

      {/* Sub-header Bar (Door count + key features) */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '2px 2px',
          gap: 8,
          whiteSpace: 'nowrap',
        }}
      >
        {/* Door Count Box */}
        <div
          style={{
            border: '1.5px solid #444444',
            display: 'inline-flex',
            alignItems: 'center',
            height: 44,
            flexShrink: 0,
          }}
        >
          <div
            style={{
              background: '#666666',
              color: '#FFFFFF',
              fontSize: 11,
              fontWeight: 800,
              padding: '0 6px',
              height: '100%',
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              lineHeight: 1.1,
            }}
          >
            <span>ドア</span>
            <span>枚数</span>
          </div>
          <div
            style={{
              padding: '0 8px',
              display: 'flex',
              alignItems: 'baseline',
            }}
          >
            <span style={{ fontSize: 36, fontWeight: 900, lineHeight: 1 }}>
              {specs.door_count || (isLarge ? 6 : 3)}
            </span>
            <span style={{ fontSize: 20, fontWeight: 900 }}>ドア</span>
          </div>
        </div>

        {/* Middle Feature Text */}
        <div
          style={{
            flex: 1,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-around',
            fontSize: isLarge ? 31 : 27,
            fontWeight: 900,
            letterSpacing: '-0.02em',
          }}
        >
          <span>
            {isLarge
              ? isCircleOk(specs.high_freshness)
                ? '高保鮮'
                : '省エネ設計'
              : isCircleOk(specs.inverter)
              ? 'インバーター'
              : specs.cooling_method || 'ファン式'}
          </span>
          <span style={{ color: '#888888', fontWeight: 400, fontSize: 26 }}>|</span>
          <span>
            {isLarge
              ? specs.middle_compartment_label || '真ん中野菜室'
              : specs.freezer_position_label || '下段冷凍室'}
          </span>
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
          {/* Left: 3D Door Layout + Dimensions */}
          <DoorDiagram3DWithDimensions
            doorLayout={String(specs.door_layout || (isLarge ? '扉5枚A' : '扉3枚'))}
            compartments={compartments}
            heightCm={specs.height_cm || (isLarge ? '185.5' : '152.0')}
            widthCm={specs.width_cm || (isLarge ? '68.5' : '54.0')}
            depthCm={specs.depth_cm || (isLarge ? '70.2' : '65.5')}
            depthBodyOnlyCm={specs.depth_body_only_cm || (isLarge ? '69.9' : '65.5')}
            showWidthBox={true}
            showFoodSpace={false}
            totalCapacityL={cap}
          />

          {/* Right Column */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6, minWidth: 0 }}>
            <DoorSwingDiagramSvg
              openType={String(specs.door_open_type || (isLarge ? 'フレンチドア' : '右開き'))}
              depthOpenCm={specs.depth_door_open_cm || (isLarge ? '105.3' : '115.9')}
            />

            {isLarge ? (
              /* >=350L Right Lower Layout: Clearance on top, Weight + Auto Ice + Smartphone below */
              <>
                <div
                  style={{
                    background: '#FFFFFF',
                    border: '1.5px solid #444444',
                    display: 'flex',
                    flexDirection: 'column',
                    whiteSpace: 'nowrap',
                  }}
                >
                  <div
                    style={{
                      background: '#666666',
                      color: '#FFFFFF',
                      fontSize: 12,
                      fontWeight: 700,
                      textAlign: 'center',
                      padding: '2px 0',
                    }}
                  >
                    放熱スペース
                  </div>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr' }}>
                    <div style={{ borderRight: '1px solid #888', textAlign: 'center' }}>
                      <div style={{ borderBottom: '1px solid #888', fontSize: 9.5, fontWeight: 700 }}>
                        左右
                      </div>
                      <div style={{ fontSize: 19, fontWeight: 800, padding: '2px 0' }}>
                        {specs.clearance_side_cm ?? 0.5}
                        <span style={{ fontSize: 11 }}>cm</span>
                      </div>
                    </div>
                    <div style={{ borderRight: '1px solid #888', textAlign: 'center' }}>
                      <div style={{ borderBottom: '1px solid #888', fontSize: 9.5, fontWeight: 700 }}>
                        上
                      </div>
                      <div style={{ fontSize: 19, fontWeight: 800, padding: '2px 0' }}>
                        {specs.clearance_top_cm ?? 5}
                        <span style={{ fontSize: 11 }}>cm</span>
                      </div>
                    </div>
                    <div style={{ textAlign: 'center' }}>
                      <div style={{ borderBottom: '1px solid #888', fontSize: 9.5, fontWeight: 700 }}>
                        背面
                      </div>
                      <div style={{ fontSize: 19, fontWeight: 800, padding: '2px 0' }}>
                        {specs.clearance_back_cm ?? 0}
                        <span style={{ fontSize: 11 }}>cm</span>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Weight + Auto Ice + Smartphone Link */}
                <div
                  style={{
                    display: 'grid',
                    gridTemplateColumns: '68px 62px 1fr',
                    gap: 4,
                    flex: 1,
                    whiteSpace: 'nowrap',
                  }}
                >
                  <div
                    style={{
                      background: '#FFFFFF',
                      border: '1.5px solid #444444',
                      display: 'flex',
                      flexDirection: 'column',
                    }}
                  >
                    <div
                      style={{
                        background: '#666666',
                        color: '#FFFFFF',
                        fontSize: 10.5,
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
                        paddingTop: 10,
                      }}
                    >
                      <span style={{ fontSize: 21, fontWeight: 800 }}>
                        {specs.weight_kg ?? 131}
                      </span>
                      <span style={{ fontSize: 11.5, fontWeight: 700 }}>kg</span>
                    </div>
                  </div>

                  <div
                    style={{
                      background: '#FFFFFF',
                      border: '1.5px solid #444444',
                      display: 'flex',
                      flexDirection: 'column',
                    }}
                  >
                    <div
                      style={{
                        background: '#666666',
                        color: '#FFFFFF',
                        fontSize: 10.5,
                        fontWeight: 700,
                        textAlign: 'center',
                        padding: '2px 0',
                      }}
                    >
                      自動製氷
                    </div>
                    <div
                      style={{
                        flex: 1,
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        fontSize: 28,
                        fontWeight: 700,
                      }}
                    >
                      {isCircleOk(specs.auto_ice) ? '◯' : '×'}
                    </div>
                  </div>

                  <div
                    style={{
                      background: '#FFFFFF',
                      border: '1.5px solid #444444',
                      display: 'flex',
                      flexDirection: 'column',
                    }}
                  >
                    <div
                      style={{
                        background: '#666666',
                        color: '#FFFFFF',
                        fontSize: 10.5,
                        fontWeight: 700,
                        textAlign: 'center',
                        padding: '2px 0',
                      }}
                    >
                      スマホ連携
                    </div>
                    <div
                      style={{
                        flex: 1,
                        display: 'grid',
                        gridTemplateColumns: '1fr 1fr',
                        alignItems: 'center',
                        padding: '2px 4px',
                      }}
                    >
                      <div
                        style={{
                          borderRight: '1px solid #CCC',
                          textAlign: 'center',
                          fontSize: 28,
                          fontWeight: 700,
                        }}
                      >
                        {isCircleOk(specs.smartphone_link) ? '◯' : '×'}
                      </div>
                      <div
                        style={{
                          display: 'flex',
                          flexDirection: 'column',
                          alignItems: 'center',
                          justifyContent: 'center',
                          opacity: isCircleOk(specs.edion_smart_app) ? 1 : 0.25,
                        }}
                      >
                        <div
                          style={{
                            border: '1.2px solid #222',
                            borderRadius: 4,
                            padding: '2px 3px',
                            fontSize: 6.5,
                            fontWeight: 800,
                            textAlign: 'center',
                            lineHeight: 1.1,
                          }}
                        >
                          スマートアプリ
                          <br />
                          対応
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </>
            ) : (
              /* <=349L Right Lower Layout: Weight + Smartphone + Clearance on top, 4 Feature Grid below */
              <>
                <div
                  style={{
                    display: 'grid',
                    gridTemplateColumns: '54px 86px 1fr',
                    gap: 4,
                    whiteSpace: 'nowrap',
                  }}
                >
                  <div
                    style={{
                      background: '#FFFFFF',
                      border: '1px solid #666',
                      display: 'flex',
                      flexDirection: 'column',
                    }}
                  >
                    <div
                      style={{
                        background: '#666',
                        color: '#FFF',
                        fontSize: 8.5,
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
                        paddingTop: 6,
                      }}
                    >
                      <span style={{ fontSize: 17, fontWeight: 800 }}>{specs.weight_kg ?? 55}</span>
                      <span style={{ fontSize: 9.5, fontWeight: 700 }}>kg</span>
                    </div>
                  </div>

                  <div
                    style={{
                      background: '#FFFFFF',
                      border: '1px solid #666',
                      display: 'flex',
                      flexDirection: 'column',
                    }}
                  >
                    <div
                      style={{
                        background: '#666',
                        color: '#FFF',
                        fontSize: 8.5,
                        fontWeight: 700,
                        textAlign: 'center',
                        padding: '2px 0',
                      }}
                    >
                      スマホ連携
                    </div>
                    <div
                      style={{
                        flex: 1,
                        display: 'grid',
                        gridTemplateColumns: '1fr 1fr',
                        alignItems: 'center',
                      }}
                    >
                      <div style={{ textAlign: 'center', fontSize: 20, fontWeight: 700 }}>
                        {isCircleOk(specs.smartphone_link) ? '◯' : '×'}
                      </div>
                      <div
                        style={{
                          fontSize: 6,
                          textAlign: 'center',
                          opacity: isCircleOk(specs.edion_smart_app) ? 1 : 0.25,
                          border: '1px solid #999',
                          margin: 2,
                          padding: 1,
                        }}
                      >
                        スマート
                        <br />
                        アプリ
                      </div>
                    </div>
                  </div>

                  <div
                    style={{
                      background: '#FFFFFF',
                      border: '1px solid #666',
                      display: 'flex',
                      flexDirection: 'column',
                    }}
                  >
                    <div
                      style={{
                        background: '#666',
                        color: '#FFF',
                        fontSize: 8.5,
                        fontWeight: 700,
                        textAlign: 'center',
                        padding: '2px 0',
                      }}
                    >
                      放熱スペース
                    </div>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', flex: 1 }}>
                      <div style={{ borderRight: '1px solid #AAA', textAlign: 'center' }}>
                        <div style={{ borderBottom: '1px solid #AAA', fontSize: 7.5 }}>左右</div>
                        <div style={{ fontSize: 13, fontWeight: 800 }}>
                          {specs.clearance_side_cm ?? 1}
                          <span style={{ fontSize: 8 }}>cm</span>
                        </div>
                      </div>
                      <div style={{ borderRight: '1px solid #AAA', textAlign: 'center' }}>
                        <div style={{ borderBottom: '1px solid #AAA', fontSize: 7.5 }}>上</div>
                        <div style={{ fontSize: 13, fontWeight: 800 }}>
                          {specs.clearance_top_cm ?? 5}
                          <span style={{ fontSize: 8 }}>cm</span>
                        </div>
                      </div>
                      <div style={{ textAlign: 'center' }}>
                        <div style={{ borderBottom: '1px solid #AAA', fontSize: 7.5 }}>背面</div>
                        <div style={{ fontSize: 13, fontWeight: 800 }}>
                          {specs.clearance_back_cm ?? 0}
                          <span style={{ fontSize: 8 }}>cm</span>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>

                {/* 4-Column Feature Grid for <=349L */}
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
                        fontSize: 9.5,
                        fontWeight: 700,
                        height: 32,
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        textAlign: 'center',
                        lineHeight: 1.15,
                      }}
                    >
                      自動
                      <br />
                      製氷
                    </div>
                    {renderFlagSymbol(specs.auto_ice, 20)}
                  </div>

                  <div style={{ borderRight: '1px solid #AAA' }}>
                    <div
                      style={{
                        background: '#666666',
                        color: '#FFFFFF',
                        fontSize: 9.5,
                        fontWeight: 700,
                        height: 32,
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        textAlign: 'center',
                        lineHeight: 1.15,
                      }}
                    >
                      自動
                      <br />
                      霜取り
                    </div>
                    {renderFlagSymbol(specs.auto_defrost, 20)}
                  </div>

                  <div style={{ borderRight: '1px solid #AAA' }}>
                    <div
                      style={{
                        background: '#666666',
                        color: '#FFFFFF',
                        fontSize: 9.5,
                        fontWeight: 700,
                        height: 32,
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        textAlign: 'center',
                        lineHeight: 1.15,
                      }}
                    >
                      冷蔵室
                      <br />
                      庫内灯
                    </div>
                    {renderFlagSymbol(specs.fridge_light, 20)}
                  </div>

                  <div>
                    <div
                      style={{
                        background: '#666666',
                        color: '#FFFFFF',
                        fontSize: 8.5,
                        fontWeight: 700,
                        height: 32,
                        display: 'flex',
                        flexDirection: 'column',
                        alignItems: 'center',
                        justifyContent: 'center',
                        textAlign: 'center',
                        lineHeight: 1.05,
                      }}
                    >
                      <span>耐熱</span>
                      <span>トップテーブル</span>
                      <span style={{ fontSize: 7 }}>(100℃)</span>
                    </div>
                    {renderFlagSymbol(specs.heat_top_table, 20)}
                  </div>
                </div>
              </>
            )}
          </div>
        </div>

        <div style={{ fontSize: 7.5, color: '#222', whiteSpace: 'nowrap' }}>
          ※表記容積は、定格内容積、食品収納スペースの目安です。2015年JISで測定。 ※高さ・幅・奥行の単位はcm。
        </div>
      </div>

      {/* Middle Row: Energy Label + Barcodes + Optional e angle Select */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: hasEAngle ? '210px 124px 1fr' : '218px 1fr',
          gap: 6,
          alignItems: 'stretch',
        }}
      >
        <UnifiedEnergyLabelBox
          star={specs.energy_star || (isLarge ? '3.5' : '2.0')}
          targetYear={specs.energy_target_year || '2021年度'}
          achievementPct={specs.energy_achievement_pct || (isLarge ? '107' : '101')}
          annualKwh={specs.annual_power_kwh || (isLarge ? '291' : '323')}
          annualBillYen={specs.annual_elec_bill_yen || (isLarge ? '7,860' : '8,720')}
        />

        {/* Color Swatches & Barcodes */}
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            justifyContent: 'space-between',
            padding: '2px 2px',
            minWidth: 0,
            overflow: 'hidden',
          }}
        >
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: specs.color2_jan && !hasEAngle ? '1fr 1fr' : '1fr',
              gap: 6,
              alignItems: 'flex-end',
            }}
          >
            {/* Color 1 */}
            <div style={{ minWidth: 0, overflow: 'hidden' }}>
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  marginBottom: 2,
                  gap: 2,
                }}
              >
                <div
                  style={{
                    fontSize: 7,
                    fontWeight: 700,
                    lineHeight: 1.15,
                    whiteSpace: 'nowrap',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                  }}
                >
                  {specs.color_name || '(TW) フロストホワイト'}
                </div>
                <div
                  style={{
                    width: 13,
                    height: 28,
                    background: 'linear-gradient(180deg, #F5F5F5 0%, #DCDCDC 100%)',
                    border: '1px solid #999',
                    flexShrink: 0,
                  }}
                />
              </div>
              <JanBarcodeSvg
                jan={String(specs.jan_code || '4904530137310')}
                width={hasEAngle ? 0.9 : 1.0}
                height={20}
              />
            </div>

            {/* Color 2 (if present & no e angle blocking) */}
            {specs.color2_jan && !hasEAngle && (
              <div style={{ minWidth: 0, overflow: 'hidden' }}>
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    marginBottom: 2,
                    gap: 2,
                  }}
                >
                  <div
                    style={{
                      fontSize: 7,
                      fontWeight: 700,
                      lineHeight: 1.15,
                      whiteSpace: 'nowrap',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                    }}
                  >
                    {specs.color2_name || '(TH) フロストグレージュ'}
                  </div>
                  <div
                    style={{
                      width: 13,
                      height: 28,
                      background: 'linear-gradient(180deg, #7B7875 0%, #524F4D 100%)',
                      border: '1px solid #555',
                      flexShrink: 0,
                    }}
                  />
                </div>
                <JanBarcodeSvg jan={String(specs.color2_jan)} width={1.0} height={20} />
              </div>
            )}
          </div>

          <div style={{ fontSize: 6.5, color: '#222', marginTop: 2, lineHeight: 1.2 }}>
            ※実際の色とは異なる場合が
            <br />
            ございます。
          </div>
        </div>

        {/* e angle Select Panel (shown on R27XN/HRD29ESW or when original points exist) */}
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

      {/* Bottom Footer: 4 Badges for >=350L OR Recycling Footer for <=349L */}
      {isLarge ? (
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: '76px 70px 78px 1fr',
            gap: 4,
            alignItems: 'stretch',
            whiteSpace: 'nowrap',
          }}
        >
          {/* 1. Long-term Warranty Badge */}
          <div
            style={{
              border: '1.5px solid #444444',
              padding: '4px 4px',
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'space-between',
              textAlign: 'center',
            }}
          >
            <div style={{ fontSize: 13, fontWeight: 900, lineHeight: 1.1 }}>
              長期
              <br />
              修理保証
            </div>
            <div
              style={{
                border: '1px solid #333',
                borderRadius: 3,
                fontSize: 8.5,
                fontWeight: 800,
                padding: '1px 4px',
                width: '92%',
              }}
            >
              Cymbal カード
            </div>
            <div style={{ display: 'flex', alignItems: 'baseline' }}>
              <span style={{ fontSize: 36, fontWeight: 900, lineHeight: 0.95 }}>
                {warrantyYears}
              </span>
              <span style={{ fontSize: 15, fontWeight: 900 }}>年</span>
            </div>
          </div>

          {/* 2. Free Delivery & Installation Badge */}
          <div
            style={{
              border: '1.5px solid #444444',
              padding: '4px 4px',
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'space-between',
              textAlign: 'center',
            }}
          >
            <div style={{ fontSize: 10.5, fontWeight: 900 }}>🚚 配達・取付</div>
            <div style={{ fontSize: 32, fontWeight: 900, lineHeight: 1.0 }}>無料</div>
            <div style={{ fontSize: 7, color: '#333' }}>※当社指定エリア</div>
          </div>

          {/* 3. Free Estimate Badge */}
          <div
            style={{
              border: '1.5px solid #444444',
              padding: '4px 4px',
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'space-between',
              textAlign: 'center',
            }}
          >
            <div style={{ fontSize: 9.5, fontWeight: 900 }}>搬入にご不安の方</div>
            <div style={{ fontSize: 18, fontWeight: 900, lineHeight: 1.05 }}>無料見積</div>
            <div style={{ fontSize: 5.8, lineHeight: 1.15, color: '#333' }}>
              特殊な搬入の場合
              <br />
              (クレーンを使用する場合など)は
              <br />
              別途追加費用がかかることも
              <br />
              ございます。
            </div>
          </div>

          {/* 4. Compact Recycling Fee Box */}
          <RecyclingFooterBar compact={true} />
        </div>
      ) : (
        <RecyclingFooterBar compact={false} />
      )}
    </div>
  );
};
