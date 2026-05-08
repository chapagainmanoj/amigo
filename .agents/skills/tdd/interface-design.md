# Interface Design for Testability

Good interfaces make testing natural:

1. **Accept dependencies, don't create them**

```typescript
   // Testable
   function processOrder(order, paymentGateway) {}

   // Hard to test
   function processOrder(order) {
     const gateway = new StripeGateway();
   }
```

```python
   # Testable
   def process_order(order, payment_gateway): ...

   # Hard to test
   def process_order(order):
       gateway = StripeGateway()
```

2. **Return results, don't produce side effects**

```typescript
   // Testable
   function calculateDiscount(cart): Discount {}

   // Hard to test
   function applyDiscount(cart): void {
     cart.total -= discount;
   }
```

```python
   # Testable
   def calculate_discount(cart) -> Discount: ...

   # Hard to test
   def apply_discount(cart) -> None:
       cart.total -= discount
```

3. **Small surface area**
   - Fewer methods = fewer tests needed
   - Fewer params = simpler test setup