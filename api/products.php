<?php
/**
 * Products API
 * 
 * Handles product retrieval from the database
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

// Handle GET request - get all products or specific product
if ($_SERVER['REQUEST_METHOD'] === 'GET') {
    
    // Get specific product by ID
    if (isset($_GET['id'])) {
        $id = intval($_GET['id']);
        $stmt = $conn->prepare("SELECT * FROM products WHERE id = ?");
        $stmt->bind_param("i", $id);
        $stmt->execute();
        $result = $stmt->get_result();
        
        if ($row = $result->fetch_assoc()) {
            echo json_encode($row);
        } else {
            http_response_code(404);
            echo json_encode(['error' => 'Product not found']);
        }
        
        $stmt->close();
    } 
    // Get products with optional filters
    else {
        $query = "SELECT * FROM products WHERE 1=1";
        $params = [];
        $types = "";
        
        // Filter by category
        if (isset($_GET['category']) && $_GET['category'] !== 'all') {
            $query .= " AND category = ?";
            $params[] = $_GET['category'];
            $types .= "s";
        }
        
        // Search by name or description
        if (isset($_GET['search']) && !empty($_GET['search'])) {
            $query .= " AND (name LIKE ? OR description LIKE ?)";
            $searchTerm = "%" . $_GET['search'] . "%";
            $params[] = $searchTerm;
            $params[] = $searchTerm;
            $types .= "ss";
        }
        
        $query .= " ORDER BY name ASC";
        
        if (!empty($params)) {
            $stmt = $conn->prepare($query);
            $stmt->bind_param($types, ...$params);
            $stmt->execute();
            $result = $stmt->get_result();
        } else {
            $result = $conn->query($query);
        }
        
        $products = [];
        while ($row = $result->fetch_assoc()) {
            $products[] = [
                'id' => (int)$row['id'],
                'name' => $row['name'],
                'description' => $row['description'],
                'price' => (float)$row['price'],
                'category' => $row['category'],
                'image' => $row['image'],
                'stock' => (int)$row['stock']
            ];
        }
        
        echo json_encode($products);
        
        if (isset($stmt)) {
            $stmt->close();
        }
    }
}

$conn->close();
?>
