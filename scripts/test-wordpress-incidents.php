<?php
// Execute only inside a disposable WordPress test instance (Playground/CI).
require_once '/wordpress/wp-load.php';
function check_ca($condition, $message) { if (!$condition) { throw new Exception('FAIL: ' . $message); } }
function request_ca($method, $route, $body = null) {
    $request = new WP_REST_Request($method, '/castrejon/v1/' . $route);
    if ($body !== null) { $request->set_header('Content-Type', 'application/json'); $request->set_body(wp_json_encode($body)); }
    return rest_do_request($request);
}
check_ca(function_exists('ca_validate'), 'plugin active');
$picture = imagecreatetruecolor(24, 24); imagefill($picture, 0, 0, imagecolorallocate($picture, 100, 140, 70));
ob_start(); imagejpeg($picture); $photo = ob_get_clean();
$id = wp_generate_uuid4();
$data = ['id' => $id, 'kind' => 'fuga', 'priority' => 'alta', 'element' => 'Prueba local', 'description' => 'Junta rota <script>alert(1)</script>',
  'observed_at' => gmdate('Y-m-d\TH:i:s\Z'), 'longitude' => -4.371848, 'latitude' => 39.834749,
  'location_source' => 'manual', 'accuracy_m' => null, 'photo_base64' => base64_encode($photo)];
wp_set_current_user(0);
check_ca(request_ca('POST','incidents',$data)->get_status() === 403, 'anonymous write denied');
$subscriber = wp_insert_user(['user_login' => 'ca_test_subscriber', 'user_pass' => wp_generate_password(24), 'role' => 'subscriber']);
wp_set_current_user($subscriber);
check_ca(request_ca('POST','incidents',$data)->get_status() === 403, 'subscriber write denied');
$staff = wp_insert_user(['user_login' => 'ca_test_staff', 'user_pass' => wp_generate_password(24), 'role' => 'castrejon_operario']);
wp_set_current_user($staff);
$created = request_ca('POST','incidents',$data);
check_ca($created->get_status() === 201, 'staff creates: ' . wp_json_encode($created->get_data()));
$public = $created->get_data();
check_ca(!isset($public['properties']['created_by'], $public['properties']['original_hash']), 'no private fields');
check_ca($public['geometry']['coordinates'] === [-4.371848,39.834749], 'EPSG:4326 preserved');
check_ca(request_ca('POST','incidents',$data)->get_status() === 200, 'idempotent retry');
$changed = $data; $changed['description'] = 'Otra descripción';
check_ca(request_ca('POST','incidents',$changed)->get_status() === 409, 'UUID collision rejected');
$changed = $data; $changed['id'] = wp_generate_uuid4(); $changed['photo_base64'] = base64_encode('<svg onload="alert(1)"/>');
check_ca(request_ca('POST','incidents',$changed)->get_status() === 422, 'invalid image rejected');
$changed = $data; $changed['id'] = wp_generate_uuid4(); $changed['created_by'] = 1;
check_ca(request_ca('POST','incidents',$changed)->get_status() === 422, 'unknown fields rejected');
$changed = $data; $changed['latitude'] = 500;
check_ca(request_ca('POST','incidents',$changed)->get_status() === 422, 'coordinates validated');
check_ca(request_ca('PATCH','incidents/'.$id,['status'=>'en_reparacion','version'=>1])->get_status() === 200, 'status update');
check_ca(request_ca('PATCH','incidents/'.$id,['status'=>'resuelta','version'=>1])->get_status() === 409, 'stale version rejected');
$closed = request_ca('PATCH','incidents/'.$id,['status'=>'resuelta','version'=>2]);
check_ca($closed->get_status() === 200 && $closed->get_data()['properties']['closed_at'], 'closure recorded');
$reopened = request_ca('PATCH','incidents/'.$id,['status'=>'pendiente','version'=>3]);
check_ca($reopened->get_data()['properties']['closed_at'] === null, 'reopen clears closure');
wp_set_current_user(0);
$listing = request_ca('GET','incidents');
check_ca($listing->get_status() === 200 && count($listing->get_data()['features']) === 1, 'anonymous public listing; no duplicates');
$download = request_ca('GET','incidents/'.$id.'/photo');
check_ca($download->get_status() === 200 && str_starts_with($download->get_data(), "\xff\xd8"), 'public JPEG');
check_ca(request_ca('PATCH','incidents/'.$id,['status'=>'resuelta','version'=>4])->get_status() === 403, 'anonymous update denied');
global $wpdb;
check_ca((int)$wpdb->get_var("SELECT count(*) FROM {$wpdb->prefix}castrejon_incident_events") === 4, 'audit excludes duplicate and rejected writes');
echo "PASS: WordPress roles, public read/photo, photo validation, idempotence, collision, coordinates, version conflicts, closure/reopen and audit\n";
