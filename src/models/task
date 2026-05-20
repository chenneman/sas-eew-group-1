class TTask:
    _next_id = 1

    def __init__(self, orders, route, agv, creation_time):
        self.id = TTask._next_id
        TTask._next_id += 1

        self.orders = orders
        self.items = [order.item for order in orders]
        self.route = route
        self.agv = agv
        self.creation_time = creation_time

    def __repr__(self):
        return f"TTask#{self.id:04d} agv={self.agv.agv_id} orders={[o.order_id for o in self.orders]}"