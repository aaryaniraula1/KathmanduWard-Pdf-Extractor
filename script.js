const map = L.map("map").setView([28.15, 85.25], 9);

L.tileLayer(
    "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
    {
        attribution: "&copy; OpenStreetMap contributors"
    }
).addTo(map);

fetch("data.geojson")
    .then((response) => {
        if (!response.ok) {
            throw new Error("Failed to load GeoJSON");
        }

        return response.json();
    })
    .then((geojson) => {
        const layer = L.geoJSON(geojson, {
            onEachFeature: (feature, layer) => {
                const name = feature.properties?.name;
                const description = feature.properties?.description;

                if (name) {
                    layer.bindPopup(
                        `<strong>${name}</strong><br>${description || ""}`
                    );
                }
            }
        }).addTo(map);

        const bounds = layer.getBounds();

        if (bounds.isValid()) {
            map.fitBounds(bounds, {
                padding: [30, 30],
                maxZoom: 10
            });
        }
    })
    .catch((error) => {
        console.error("GeoJSON error:", error);
    });