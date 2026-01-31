# Refactored Generate Document Endpoint

## Key Changes

1. **ID-Based Payload Support**: Accepts explicit IDs for all entities
2. **Prefix-Based Matching**: Uses strict prefix rules for placeholder mapping
3. **No Auto-Sync**: Only fetches data when IDs are explicitly provided
4. **Bank Account Logic**: Handles is_primary fallback

## New Payload Structure

```json
{
  "template_id": "uuid",
  "vessel_imo": "1234567",  // Required for backward compatibility
  "vessel_id": 12,  // Optional - explicit vessel ID
  "buyer_id": "uuid",
  "seller_id": "uuid",
  "product_id": "uuid",
  "refinery_id": "uuid",
  "buyer_bank_id": "uuid",  // Optional - if not provided, uses is_primary=true
  "seller_bank_id": "uuid",  // Optional - if not provided, uses is_primary=true
  "departure_port_id": 45,
  "destination_port_id": 78,
  "broker_id": "uuid",
  "deal_id": "uuid",
  "company_id": 123
}
```

## Implementation Steps

1. Import id_based_fetcher module ✅
2. Replace vessel fetching with fetch_all_entities()
3. Replace placeholder matching with prefix-based get_placeholder_value()
4. Update placeholder replacement logic
5. Maintain backward compatibility with vessel_imo
