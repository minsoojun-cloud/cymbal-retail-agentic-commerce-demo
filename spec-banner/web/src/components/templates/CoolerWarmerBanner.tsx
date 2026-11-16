import React from 'react';

export const CoolerWarmerBanner: React.FC<{ specs: Record<string, any> }> = ({ specs }) => {
  const cellHeader: React.CSSProperties = {
    background: '#666666',
    color: '#FFFFFF',
    fontWeight: 700,
    fontSize: 15,
    height: 26,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    textAlign: 'center',
    padding: '0 6px',
    lineHeight: 1,
    boxSizing: 'border-box',
  };

  const renderPowerCircle = (val: any) => {
    const isOk = ['○', '〇', '◯', 'O', '1', 'true'].includes(String(val || '○').trim());
    if (isOk) {
      return (
        <div
          style={{
            width: 28,
            height: 28,
            borderRadius: '50%',
            border: '2px solid #222222',
            margin: '4px auto 2px',
          }}
        />
      );
    }
    return (
      <div style={{ fontSize: 28, fontWeight: 700, lineHeight: 1.1, textAlign: 'center' }}>×</div>
    );
  };

  return (
    <div
      style={{
        width: 460,
        background: '#E8E8E8',
        border: '1.5px solid #666666',
        fontFamily: "'BIZ UDPGothic', sans-serif",
        color: '#1A1A1A',
        boxSizing: 'border-box',
        userSelect: 'none',
      }}
    >
      {/* Teal Header (#007A70) */}
      <div
        style={{
          background: '#007A70',
          color: '#FFFFFF',
          padding: '10px 16px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
        }}
      >
        <div style={{ fontSize: 32, fontWeight: 900, letterSpacing: '0.02em' }}>
          {specs.cooling_type || 'ペルチェ方式'}
        </div>
        <div style={{ textAlign: 'right', lineHeight: 1.25 }}>
          <div style={{ fontSize: 12, fontWeight: 700 }}>{specs.maker || 'VERSOS'}</div>
          <div style={{ fontSize: 15, fontWeight: 800 }}>{specs.model_no || 'VS442'}</div>
        </div>
      </div>

      {/* Main Content */}
      <div style={{ padding: 12, display: 'flex', flexDirection: 'column', gap: 10 }}>
        {/* Row 1: Capacity (24L) | Storage Guide (PET 500ml / Can 350ml) */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: '1fr 1fr',
            gap: 10,
          }}
        >
          <div
            style={{
              background: '#FFFFFF',
              border: '1px solid #666666',
              display: 'flex',
              flexDirection: 'column',
            }}
          >
            <div style={cellHeader}>容量</div>
            <div
              style={{
                flex: 1,
                minHeight: 118,
                display: 'flex',
                alignItems: 'baseline',
                justifyContent: 'center',
                paddingTop: 8,
              }}
            >
              <span style={{ fontSize: 92, fontWeight: 700, lineHeight: 0.95 }}>
                {specs.capacity_l ?? 24}
              </span>
              <span style={{ fontSize: 42, fontWeight: 700, marginLeft: 4 }}>L</span>
            </div>
          </div>

          <div
            style={{
              background: '#FFFFFF',
              border: '1px solid #666666',
              display: 'flex',
              flexDirection: 'column',
            }}
          >
            <div style={cellHeader}>収納目安</div>
            <div style={{ flex: 1, display: 'grid', gridTemplateColumns: '1fr 1fr' }}>
              <div
                style={{
                  borderRight: '1px solid #888888',
                  display: 'flex',
                  flexDirection: 'column',
                }}
              >
                <div
                  style={{
                    borderBottom: '1px solid #888888',
                    padding: '4px 2px',
                    textAlign: 'center',
                    fontSize: 11.5,
                    fontWeight: 700,
                    lineHeight: 1.2,
                  }}
                >
                  ペットボトル
                  <br />
                  (500ml)
                </div>
                <div
                  style={{
                    flex: 1,
                    display: 'flex',
                    alignItems: 'baseline',
                    justifyContent: 'center',
                    paddingTop: 12,
                  }}
                >
                  <span style={{ fontSize: 46, fontWeight: 700, lineHeight: 1 }}>
                    {specs.pet_500ml_count ?? 14}
                  </span>
                  <span style={{ fontSize: 22, fontWeight: 700, marginLeft: 2 }}>本</span>
                </div>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column' }}>
                <div
                  style={{
                    borderBottom: '1px solid #888888',
                    padding: '4px 2px',
                    textAlign: 'center',
                    fontSize: 11.5,
                    fontWeight: 700,
                    lineHeight: 1.2,
                  }}
                >
                  缶
                  <br />
                  (350ml)
                </div>
                <div
                  style={{
                    flex: 1,
                    display: 'flex',
                    alignItems: 'baseline',
                    justifyContent: 'center',
                    paddingTop: 12,
                  }}
                >
                  <span style={{ fontSize: 46, fontWeight: 700, lineHeight: 1 }}>
                    {specs.can_350ml_count ?? 17}
                  </span>
                  <span style={{ fontSize: 22, fontWeight: 700, marginLeft: 2 }}>本</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Row 2: Temperature (Cool / Warm) | Power (AC / DC + cord length) */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: '1fr 1fr',
            gap: 10,
          }}
        >
          <div style={{ background: '#FFFFFF', border: '1px solid #666666' }}>
            <div style={cellHeader}>温度</div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', height: 86 }}>
              <div
                style={{
                  borderRight: '1px solid #888888',
                  display: 'flex',
                  flexDirection: 'column',
                }}
              >
                <div
                  style={{
                    borderBottom: '1px solid #888888',
                    textAlign: 'center',
                    fontSize: 13,
                    fontWeight: 700,
                    padding: '2px 0',
                  }}
                >
                  保冷
                </div>
                <div
                  style={{
                    flex: 1,
                    display: 'flex',
                    alignItems: 'baseline',
                    justifyContent: 'center',
                    paddingTop: 10,
                    gap: 2,
                  }}
                >
                  <span style={{ fontSize: 15, fontWeight: 700 }}>約</span>
                  <span style={{ fontSize: 34, fontWeight: 700, lineHeight: 1 }}>
                    {specs.cool_temp_c ?? '-9'}
                  </span>
                  <span style={{ fontSize: 20, fontWeight: 700 }}>℃</span>
                </div>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column' }}>
                <div
                  style={{
                    borderBottom: '1px solid #888888',
                    textAlign: 'center',
                    fontSize: 13,
                    fontWeight: 700,
                    padding: '2px 0',
                  }}
                >
                  保温
                </div>
                <div
                  style={{
                    flex: 1,
                    display: 'flex',
                    alignItems: 'baseline',
                    justifyContent: 'center',
                    paddingTop: 10,
                    gap: 2,
                  }}
                >
                  <span style={{ fontSize: 15, fontWeight: 700 }}>約</span>
                  <span style={{ fontSize: 34, fontWeight: 700, lineHeight: 1 }}>
                    {specs.warm_temp_c ?? '60'}
                  </span>
                  <span style={{ fontSize: 20, fontWeight: 700 }}>℃</span>
                </div>
              </div>
            </div>
          </div>

          <div style={{ background: '#FFFFFF', border: '1px solid #666666' }}>
            <div style={cellHeader}>電源</div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', height: 86 }}>
              <div
                style={{
                  borderRight: '1px solid #888888',
                  display: 'flex',
                  flexDirection: 'column',
                }}
              >
                <div
                  style={{
                    borderBottom: '1px solid #888888',
                    textAlign: 'center',
                    fontSize: 13,
                    fontWeight: 700,
                    padding: '2px 0',
                  }}
                >
                  AC
                </div>
                <div
                  style={{
                    flex: 1,
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'center',
                    justifyContent: 'center',
                  }}
                >
                  {renderPowerCircle(specs.power_ac)}
                  {specs.cord_ac_m && (
                    <div style={{ fontSize: 10, fontWeight: 700 }}>
                      (コード長:{specs.cord_ac_m}m)
                    </div>
                  )}
                </div>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column' }}>
                <div
                  style={{
                    borderBottom: '1px solid #888888',
                    textAlign: 'center',
                    fontSize: 13,
                    fontWeight: 700,
                    padding: '2px 0',
                  }}
                >
                  DC
                </div>
                <div
                  style={{
                    flex: 1,
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'center',
                    justifyContent: 'center',
                  }}
                >
                  {renderPowerCircle(specs.power_dc)}
                  {specs.cord_dc_m && (
                    <div style={{ fontSize: 10, fontWeight: 700 }}>
                      (コード長:{specs.cord_dc_m}m)
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Row 3: Body Size (mm) | Weight (kg) */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: '3fr 1.05fr',
            gap: 10,
          }}
        >
          <div style={{ background: '#FFFFFF', border: '1px solid #666666' }}>
            <div style={cellHeader}>商品本体サイズ(mm)</div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', height: 60 }}>
              <div
                style={{
                  borderRight: '1px solid #888888',
                  display: 'flex',
                  flexDirection: 'column',
                }}
              >
                <div
                  style={{
                    borderBottom: '1px solid #888888',
                    fontSize: 10,
                    fontWeight: 700,
                    textAlign: 'center',
                    lineHeight: '15px',
                  }}
                >
                  横幅
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
                  {specs.width_mm ?? 310}
                </div>
              </div>

              <div
                style={{
                  borderRight: '1px solid #888888',
                  display: 'flex',
                  flexDirection: 'column',
                }}
              >
                <div
                  style={{
                    borderBottom: '1px solid #888888',
                    fontSize: 10,
                    fontWeight: 700,
                    textAlign: 'center',
                    lineHeight: '15px',
                  }}
                >
                  高さ
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
                  {specs.height_mm ?? 460}
                </div>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column' }}>
                <div
                  style={{
                    borderBottom: '1px solid #888888',
                    fontSize: 10,
                    fontWeight: 700,
                    textAlign: 'center',
                    lineHeight: '15px',
                  }}
                >
                  奥行
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
                  {specs.depth_mm ?? 375}
                </div>
              </div>
            </div>
          </div>

          <div style={{ background: '#FFFFFF', border: '1px solid #666666' }}>
            <div style={cellHeader}>重量(kg)</div>
            <div
              style={{
                height: 60,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: 32,
                fontWeight: 700,
              }}
            >
              {specs.weight_kg ?? '8.0'}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
