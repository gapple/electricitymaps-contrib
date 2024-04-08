/* eslint-disable unicorn/no-null */
import MobileTooltipWrapper from 'components/tooltips/MobileTooltipWrapper';
import TooltipWrapper from 'components/tooltips/TooltipWrapper';
import { getHeaderHeight } from 'features/charts/bar-breakdown/utils';
import { mapMovingAtom } from 'features/map/mapAtoms';
import { useSetAtom } from 'jotai';
import { useEffect, useMemo } from 'react';
import { resolvePath } from 'react-router-dom';
import { ExchangeArrowData } from 'types';

import ExchangeTooltip from './ExchangeTooltip';
import MobileExchangeTooltip from './MobileExchangeTooltip';
import { quantizedCo2IntensityScale, quantizedExchangeSpeedScale } from './scales';

interface ExchangeArrowProps {
  data: ExchangeArrowData;
  viewportWidth: number;
  viewportHeight: number;
  map: maplibregl.Map;
  colorBlindMode: boolean;
}

function ExchangeArrow({
  data,
  viewportWidth,
  viewportHeight,
  map,
  colorBlindMode,
}: ExchangeArrowProps) {
  const mapZoom = map.getZoom();
  const colorBlindModeEnabled = colorBlindMode;
  const absFlow = Math.abs(data.netFlow ?? 0);
  const { co2intensity, lonlat, netFlow, rotation, key } = data;
  const setIsMoving = useSetAtom(mapMovingAtom);
  const headerHeight = getHeaderHeight();
  if (!lonlat) {
    return null;
  }

  useEffect(() => {
    const cancelWheel = (event: Event) => event.preventDefault();
    const exchangeLayer = document.querySelector('#exchange-layer');
    if (!exchangeLayer) {
      return;
    }
    exchangeLayer.addEventListener('wheel', cancelWheel, {
      passive: false,
    });
    return () => exchangeLayer.removeEventListener('wheel', cancelWheel);
  }, []);

  const imageSource = useMemo(() => {
    const prefix = colorBlindModeEnabled ? 'colorblind-' : '';
    const intensity = quantizedCo2IntensityScale(co2intensity);
    const speed = quantizedExchangeSpeedScale(Math.abs(netFlow));
    return resolvePath(`images/arrows/${prefix}arrow-${intensity}-animated-${speed}`)
      .pathname;
  }, [colorBlindModeEnabled, co2intensity, netFlow]);

  const projection = map.project(lonlat);

  const transform = {
    x: projection.x,
    y: projection.y,
    k: 0.04 + (mapZoom - 1.5) * 0.1,
    r: rotation + (netFlow > 0 ? 180 : 0),
  };

  // Setting the top position from the arrow tooltip preventing overflowing to top.
  let tooltipClassName = 'max-h-[256px] max-w-[512px] hidden md:flex';
  tooltipClassName += transform.y - 76 < headerHeight ? ' top-[76px]' : ' top-[-76px]';

  // Don't render if the flow is very low ...
  if (absFlow < 1) {
    return null;
  }

  // ... or if the arrow would be very tiny ...
  if (transform.k < 0.1) {
    return null;
  }

  // ... or if it would be rendered outside of viewport.
  if (transform.x + 100 * transform.k < 0) {
    return null;
  }

  if (transform.y + 100 * transform.k < 0) {
    return null;
  }

  if (transform.x - 100 * transform.k > viewportWidth) {
    return null;
  }

  if (transform.y - 100 * transform.k > viewportHeight) {
    return null;
  }

  return (
    <>
      <MobileTooltipWrapper
        tooltipClassName="flex max-h-[256px] max-w-[512px]"
        tooltipContent={<MobileExchangeTooltip exchangeData={data} />}
        side="top"
        sideOffset={10}
      >
        <picture
          id={key}
          className="md:hidden"
          style={{
            transform: `translateX(${transform.x}px) translateY(${transform.y}px) rotate(${transform.r}deg) scale(${transform.k})`,
            cursor: 'pointer',
            overflow: 'hidden',
            position: 'absolute',
            pointerEvents: 'all',
            imageRendering: 'crisp-edges',
            left: '-25px',
            top: '-41px',
          }}
          onWheel={() => setIsMoving(true)}
        >
          <source srcSet={`${imageSource}.webp`} type="image/webp" />
          <img src={`${imageSource}.gif`} alt="" draggable={false} />
        </picture>
      </MobileTooltipWrapper>
      <TooltipWrapper
        tooltipClassName={tooltipClassName}
        tooltipContent={<ExchangeTooltip exchangeData={data} />}
        side="right"
        sideOffset={10}
      >
        <picture
          id={key}
          className="hidden md:block"
          style={{
            transform: `translateX(${transform.x}px) translateY(${transform.y}px) rotate(${transform.r}deg) scale(${transform.k})`,
            cursor: 'pointer',
            overflow: 'hidden',
            position: 'absolute',
            pointerEvents: 'all',
            imageRendering: 'crisp-edges',
            left: '-25px',
            top: '-41px',
          }}
          onWheel={() => setIsMoving(true)}
        >
          <source srcSet={`${imageSource}.webp`} type="image/webp" />
          <img src={`${imageSource}.gif`} alt="" draggable={false} />
        </picture>
      </TooltipWrapper>
    </>
  );
}

export default ExchangeArrow;
