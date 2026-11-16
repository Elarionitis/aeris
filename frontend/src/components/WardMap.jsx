import React, { useEffect, useMemo } from 'react';
import { GeoJSON, MapContainer, TileLayer, useMap } from 'react-leaflet';
import { bandColor } from '../lib/aqi';

const BENGALURU_CENTRE = [12.9716, 77.5946];

/** Pans the map when the selected ward changes. */
function MapFocus({ ward }) {
  const map = useMap();
  useEffect(() => {
    if (ward?.latitude != null && ward?.longitude != null) {
      map.flyTo([ward.latitude, ward.longitude], 14, { duration: 0.7 });
    }
  }, [map, ward?.ward_id]);
  return null;
}

export function WardMap({ wards, bands, selectedWardId, onSelectWard }) {
  const selectedWard = wards.find((ward) => ward.ward_id === selectedWardId);

  // Keying the GeoJSON layer by selection forces Leaflet to restyle it; the
  // layer caches its style function otherwise.
  const geoJson = useMemo(
    () => ({
      type: 'FeatureCollection',
      features: wards
        .filter((ward) => ward.geometry)
        .map((ward) => ({
          type: 'Feature',
          properties: {
            ward_id: ward.ward_id,
            ward_name: ward.ward_name,
            aqi: ward.aqi,
            band: ward.band,
          },
          geometry: ward.geometry,
        })),
    }),
    [wards],
  );

  function styleFeature(feature) {
    const isSelected = feature?.properties?.ward_id === selectedWardId;
    const color = bandColor(feature?.properties?.aqi ?? 0, bands);
    return {
      color,
      weight: isSelected ? 3.5 : 1.2,
      fillColor: color,
      fillOpacity: isSelected ? 0.55 : 0.3,
    };
  }

  function onEachFeature(feature, layer) {
    layer.on({ click: () => onSelectWard(feature.properties.ward_id) });
    layer.bindTooltip(
      `${feature.properties.ward_name} · AQI ${feature.properties.aqi} (${feature.properties.band})`,
      { sticky: true },
    );
  }

  return (
    <div className="h-[22rem] overflow-hidden rounded-xl border border-line sm:h-[26rem]">
      <MapContainer
        center={BENGALURU_CENTRE}
        zoom={11}
        scrollWheelZoom={false}
        className="h-full w-full"
      >
        <TileLayer
          attribution="&copy; OpenStreetMap contributors"
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        <MapFocus ward={selectedWard} />
        <GeoJSON
          key={`wards-${selectedWardId}-${wards.length}`}
          data={geoJson}
          style={styleFeature}
          onEachFeature={onEachFeature}
        />
      </MapContainer>
    </div>
  );
}
