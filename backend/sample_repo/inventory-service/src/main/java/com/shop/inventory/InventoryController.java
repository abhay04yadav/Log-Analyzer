package com.shop.inventory;

import org.springframework.web.bind.annotation.*;


@RestController
@RequestMapping("/inventory")
public class InventoryController {

    private final StockService stockService;

    public InventoryController(StockService stockService) {
        this.stockService = stockService;
    }

    @PostMapping("/reserve")
    public ReservationResult reserve(@RequestBody ReservationRequest request) {
        return stockService.reserve(request.getSku(), request.getQuantity(), request.getRegion());
    }
}
