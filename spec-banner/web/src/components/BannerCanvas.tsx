import React from 'react';
import { CategoryField, CategoryId, TemplateSchema } from '../types';
import { DynamicBannerCanvas } from './DynamicBannerCanvas';
import { TvBanner } from './templates/TvBanner';
import { PcBanner } from './templates/PcBanner';
import { WineCellarBanner } from './templates/WineCellarBanner';
import { CoolerWarmerBanner } from './templates/CoolerWarmerBanner';
import { FreezerBanner } from './templates/FreezerBanner';
import { RefrigeratorBanner } from './templates/RefrigeratorBanner';

export const BannerCanvas: React.FC<{
  category: CategoryId;
  specs: Record<string, any>;
  canvasRef: React.RefObject<HTMLDivElement>;
  customTemplate?: TemplateSchema | null;
  fields?: CategoryField[];
}> = ({ category, specs, canvasRef, customTemplate, fields = [] }) => {
  const dummyRef = React.useRef<HTMLDivElement | null>(null);

  if (customTemplate) {
    return (
      <div
        ref={canvasRef}
        style={{
          display: 'inline-block',
          background: '#FFFFFF',
          boxShadow: '0 10px 30px rgba(15, 23, 42, 0.14)',
        }}
      >
        <DynamicBannerCanvas
          template={customTemplate}
          specs={specs}
          fields={fields}
          canvasRef={dummyRef}
          selectedBoxId={null}
          selectedHeaderSlot={null}
          highlightedFieldKey={null}
          showGrid={false}
          overlayOpacity={0}
          interactive={false}
          onSelectBox={() => {}}
          onSelectHeaderSlot={() => {}}
          onUpdateBox={() => {}}
          onBindFieldToBox={() => {}}
          onBindFieldToHeaderSlot={() => {}}
        />
      </div>
    );
  }

  return (
    <div
      ref={canvasRef}
      style={{
        display: 'inline-block',
        background: '#FFFFFF',
        boxShadow: '0 10px 30px rgba(15, 23, 42, 0.14)',
      }}
    >
      {category === 'tv' && <TvBanner specs={specs} />}
      {category === 'pc' && <PcBanner specs={specs} />}
      {category === 'wine_cellar' && <WineCellarBanner specs={specs} />}
      {category === 'cooler_warmer' && <CoolerWarmerBanner specs={specs} />}
      {category === 'freezer' && <FreezerBanner specs={specs} />}
      {category === 'refrigerator' && <RefrigeratorBanner specs={specs} />}
    </div>
  );
};
