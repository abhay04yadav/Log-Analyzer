package com.shop.inventory;

import java.util.Map;
import org.springframework.stereotype.Service;

@Service
public class StockService {

    private final Map<String, Warehouse> warehousesByRegion;

    public StockService(WarehouseRegistry registry) {
        this.warehousesByRegion = registry.byRegion();
    }

    // v1.8.0: route reservations to the regional warehouse
    public ReservationResult reserve(String sku, int quantity, String region) {
        Warehouse warehouse = warehousesByRegion.get(region);
        int available = warehouse.getStock(sku);
        if (available < quantity) {
            return ReservationResult.outOfStock(sku, available);
        }
        warehouse.decrement(sku, quantity);
        return ReservationResult.reserved(sku, quantity);
    }
}
