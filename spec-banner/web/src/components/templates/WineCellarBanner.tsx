import React from 'react';

export const WineCellarBanner: React.FC<{ specs: Record<string, any> }> = ({ specs }) => {
  const hasDualTemp = Boolean(
    (specs.temp_range_upper && String(specs.temp_range_upper).trim() !== '') ||
      (specs.temp_range_lower && String(specs.temp_range_lower).trim() !== '')
  );

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
          <div style={{ fontSize: 12, fontWeight: 700 }}>{specs.maker || 'アイリスオーヤマ'}</div>
          <div style={{ fontSize: 16, fontWeight: 800 }}>{specs.model_no || 'IWCP081AB'}</div>
        </div>
      </div>

      {/* Main Content */}
      <div style={{ padding: 12, display: 'flex', flexDirection: 'column', gap: 10 }}>
        {/* Row 1: Capacity | Bottle Count | Shelf Adjust */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: '1fr 1fr 1fr',
            gap: 10,
          }}
        >
          <div style={{ background: '#FFFFFF', border: '1px solid #666666' }}>
            <div style={cellHeader}>容量</div>
            <div
              style={{
                height: 76,
                display: 'flex',
                alignItems: 'baseline',
                justifyContent: 'center',
                paddingTop: 6,
              }}
            >
              <span style={{ fontSize: 56, fontWeight: 700, lineHeight: 1 }}>
                {specs.capacity_l ?? 25}
              </span>
              <span style={{ fontSize: 28, fontWeight: 700, marginLeft: 4 }}>L</span>
            </div>
          </div>

          <div style={{ background: '#FFFFFF', border: '1px solid #666666' }}>
            <div style={cellHeader}>基本収納本数</div>
            <div
              style={{
                height: 76,
                display: 'flex',
                alignItems: 'baseline',
                justifyContent: 'center',
                paddingTop: 6,
              }}
            >
              <span style={{ fontSize: 56, fontWeight: 700, lineHeight: 1 }}>
                {specs.bottle_count ?? 8}
              </span>
              <span style={{ fontSize: 24, fontWeight: 700, marginLeft: 4 }}>本</span>
            </div>
          </div>

          <div style={{ background: '#FFFFFF', border: '1px solid #666666' }}>
            <div style={cellHeader}>棚調整</div>
            <div
              style={{
                height: 76,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: 42,
                fontWeight: 700,
              }}
            >
              {specs.shelf_adjustable || '×'}
            </div>
          </div>
        </div>

        {/* Row 2: Temperature Range (Single or Upper/Lower split) | Temp Maintain */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: '2fr 1fr',
            gap: 10,
          }}
        >
          <div style={{ background: '#FFFFFF', border: '1px solid #666666' }}>
            <div style={cellHeader}>庫内温度設定範囲</div>
            {hasDualTemp ? (
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', height: 58 }}>
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
                      fontSize: 10.5,
                      fontWeight: 700,
                      textAlign: 'center',
                      lineHeight: '16px',
                    }}
                  >
                    上室
                  </div>
                  <div
                    style={{
                      flex: 1,
                      display: 'flex',
                      alignItems: 'baseline',
                      justifyContent: 'center',
                      paddingTop: 4,
                    }}
                  >
                    <span style={{ fontSize: 28, fontWeight: 700, lineHeight: 1 }}>
                      {specs.temp_range_upper || '-5〜25'}
                    </span>
                    <span style={{ fontSize: 18, fontWeight: 700, marginLeft: 2 }}>℃</span>
                  </div>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column' }}>
                  <div
                    style={{
                      borderBottom: '1px solid #888888',
                      fontSize: 10.5,
                      fontWeight: 700,
                      textAlign: 'center',
                      lineHeight: '16px',
                    }}
                  >
                    下室
                  </div>
                  <div
                    style={{
                      flex: 1,
                      display: 'flex',
                      alignItems: 'baseline',
                      justifyContent: 'center',
                      paddingTop: 4,
                    }}
                  >
                    <span style={{ fontSize: 28, fontWeight: 700, lineHeight: 1 }}>
                      {specs.temp_range_lower || '0〜25'}
                    </span>
                    <span style={{ fontSize: 18, fontWeight: 700, marginLeft: 2 }}>℃</span>
                  </div>
                </div>
              </div>
            ) : (
              <div
                style={{
                  height: 58,
                  display: 'flex',
                  alignItems: 'baseline',
                  justifyContent: 'center',
                  paddingTop: 8,
                }}
              >
                <span style={{ fontSize: 36, fontWeight: 700, lineHeight: 1 }}>
                  {specs.temp_range_single || '5〜20'}
                </span>
                <span style={{ fontSize: 24, fontWeight: 700, marginLeft: 3 }}>℃</span>
              </div>
            )}
          </div>

          <div style={{ background: '#FFFFFF', border: '1px solid #666666' }}>
            <div style={cellHeader}>温度維持</div>
            <div
              style={{
                height: 58,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: 38,
                fontWeight: 700,
              }}
            >
              {specs.temp_maintain || '×'}
            </div>
          </div>
        </div>

        {/* Row 3: Annual Power | 1-Year Electricity Bill */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: '1fr 1fr',
            gap: 10,
          }}
        >
          <div style={{ background: '#FFFFFF', border: '1px solid #666666' }}>
            <div style={cellHeader}>年間消費電力量</div>
            <div
              style={{
                height: 62,
                display: 'flex',
                alignItems: 'baseline',
                justifyContent: 'center',
                paddingTop: 8,
              }}
            >
              <span style={{ fontSize: 38, fontWeight: 700, lineHeight: 1 }}>
                {specs.annual_power_kwh ?? 100}
              </span>
              <span style={{ fontSize: 20, fontWeight: 700, marginLeft: 4 }}>kWh/年</span>
            </div>
          </div>

          <div style={{ background: '#FFFFFF', border: '1px solid #666666' }}>
            <div style={cellHeader}>1年間電気代目安</div>
            <div
              style={{
                height: 62,
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'baseline' }}>
                <span style={{ fontSize: 36, fontWeight: 700, lineHeight: 1 }}>
                  {specs.annual_elec_bill_yen || '1,263'}
                </span>
                <span style={{ fontSize: 20, fontWeight: 700, marginLeft: 3 }}>円</span>
                <span style={{ fontSize: 10, fontWeight: 700 }}>(税込)</span>
              </div>
              <div style={{ fontSize: 8.5, color: '#333', marginTop: 2 }}>
                ※使用の状況により数値は異なります
              </div>
            </div>
          </div>
        </div>

        {/* Row 4: Body Size (mm) | Weight (kg) */}
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
                  {specs.width_mm ?? 252}
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
                  {specs.height_mm ?? 450}
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
                  {specs.depth_mm ?? 500}
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
              {specs.weight_kg ?? '9.5'}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
