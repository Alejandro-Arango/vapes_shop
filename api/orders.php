<?php
/**
 * Orders API
 * 
 * Handles order creation and retrieval
 */

require_once 'config.php';

header('Content-Type: application/json');

// Get database connection
$conn = getDbConnection();

if (!$conn) {
    http_response_code(500);
    echo json_encode(['error' => 'Database connection failed']);
    exit();
}

// Handle POST request - create new order
if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    
    // Get JSON input
    $input = file_get_contents('php://input');
    $data = json_decode($input, true);
    
    if (!isset($data['items']) || !is_array($data['items']) || empty($data['items'])) {
        http_response_code(400);
        echo json_encode(['error' => 'Invalid order data']);
        exit();
    }
    
    // Start transaction
    $conn->begin_transaction();
    
    try {
        // Calculate total
        $total = 0;
        foreach ($data['items'] as $item) {
            $total += $item['price'] * $item['quantity'];
        }
        
        // Insert order
        $stmt = $conn->prepare("INSERT INTO orders (total_amount, status) VALUES (?, 'pending')");
        $stmt->bind_param("d", $total);
        $stmt->execute();
        $orderId = $conn->insert_id;
        $stmt->close();
        
        // Insert order items
        $stmt = $conn->prepare("INSERT INTO order_items (order_id, product_id, product_name, quantity, price, subtotal) VALUES (?, ?, ?, ?, ?, ?)");
        
        foreach ($data['items'] as $item) {
            $productId = $item['id'];
            $productName = $item['name'];
            $quantity = $item['quantity'];
            $price = $item['price'];
            $subtotal = $price * $quantity;
            
            $stmt->bind_param("iisids", $orderId, $productId, $productName, $quantity, $price, $subtotal);
            $stmt->execute();
        }
        
        $stmt->close();
        
        // Commit transaction
        $conn->commit();
        
        http_response_code(201);
        echo json_encode([
            'success' => true,
            'orderId' => $orderId,
            'total' => $total,
            'message' => 'Order created successfully'
        ]);
        
    } catch (Exception $e) {
        // Rollback on error
        $conn->rollback();
        
        http_response_code(500);
        echo json_encode([
            'error' => 'Failed to create order',
            'message' => $e->getMessage()
        ]);
    }
}

// Handle GET request - get order by ID
elseif ($_SERVER['REQUEST_METHOD'] === 'GET') {
    
    if (isset($_GET['id'])) {
        $id = intval($_GET['id']);
        
        // Get order details
        $stmt = $conn->prepare("SELECT * FROM orders WHERE id = ?");
        $stmt->bind_param("i", $id);
        $stmt->execute();
        $result = $stmt->get_result();
        
        if ($order = $result->fetch_assoc()) {
            $stmt->close();
            
            // Get order items
            $stmt = $conn->prepare("SELECT * FROM order_items WHERE order_id = ?");
            $stmt->bind_param("i", $id);
            $stmt->execute();
            $itemsResult = $stmt->get_result();
            
            $items = [];
            while ($item = $itemsResult->fetch_assoc()) {
                $items[] = $item;
            }
            
            $order['items'] = $items;
            
            echo json_encode($order);
            $stmt->close();
        } else {
            http_response_code(404);
            echo json_encode(['error' => 'Order not found']);
        }
    } else {
        http_response_code(400);
        echo json_encode(['error' => 'Order ID is required']);
    }
}

$conn->close();
?>
