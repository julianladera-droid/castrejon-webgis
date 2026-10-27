<?php
/**
 * Plugin Name: Castrejón · Averías
 * Description: Captura móvil de averías con foto y GPS; capa pública para el visor de Castrejón.
 * Version: 1.0.0
 * Requires at least: 6.6
 * Requires PHP: 8.1
 * License: GPL-2.0-or-later
 */
if (!defined('ABSPATH')) { exit; }
require_once __DIR__ . '/domain.php';

const CA_CAP = 'manage_castrejon_incidents';
const CA_NS = 'castrejon/v1';

function ca_routes() {
    add_rewrite_rule('^averias-campo/?$', 'index.php?ca_app=1', 'top');
    add_rewrite_rule('^averias-campo/session/?$', 'index.php?ca_session=1', 'top');
    add_rewrite_rule('^averias-campo/sw.js$', 'index.php?ca_sw=1', 'top');
}
add_action('init', 'ca_routes');
add_filter('query_vars', function ($vars) { return array_merge($vars, ['ca_app', 'ca_session', 'ca_sw']); });

function ca_activate() {
    if (!extension_loaded('gd')) { wp_die('Castrejón Averías requiere la extensión PHP GD para normalizar fotografías.'); }
    global $wpdb;
    require_once ABSPATH . 'wp-admin/includes/upgrade.php';
    $table = $wpdb->prefix . 'castrejon_incidents';
    $events = $wpdb->prefix . 'castrejon_incident_events';
    $collation = $wpdb->get_charset_collate();
    dbDelta("CREATE TABLE $table (
      id char(36) NOT NULL,
      public_data longtext NOT NULL,
      photo longblob NOT NULL,
      original_hash char(64) NOT NULL,
      status varchar(20) NOT NULL DEFAULT 'pendiente',
      version bigint unsigned NOT NULL DEFAULT 1,
      created_at datetime NOT NULL,
      updated_at datetime NOT NULL,
      closed_at datetime DEFAULT NULL,
      created_by bigint unsigned NOT NULL,
      PRIMARY KEY  (id),
      KEY status (status)
    ) ENGINE=InnoDB $collation;");
    dbDelta("CREATE TABLE $events (
      id bigint unsigned NOT NULL AUTO_INCREMENT,
      incident_id char(36) NOT NULL,
      staff_id bigint unsigned NOT NULL,
      status varchar(20) NOT NULL,
      version bigint unsigned NOT NULL,
      changed_at datetime NOT NULL,
      PRIMARY KEY  (id),
      KEY incident_id (incident_id)
    ) ENGINE=InnoDB $collation;");
    if ($wpdb->get_var($wpdb->prepare('SHOW TABLES LIKE %s', $table)) !== $table ||
        $wpdb->get_var($wpdb->prepare('SHOW TABLES LIKE %s', $events)) !== $events) {
        wp_die('No se pudieron crear las tablas de averías.');
    }
    add_role('castrejon_operario', 'Operario de averías', ['read' => true, CA_CAP => true]);
    $admin = get_role('administrator');
    if ($admin) { $admin->add_cap(CA_CAP); }
    ca_routes();
    flush_rewrite_rules();
}
register_activation_hook(__FILE__, 'ca_activate');
register_deactivation_hook(__FILE__, 'flush_rewrite_rules');
// Deliberately no uninstall data deletion: operational records must survive plugin removal.

function ca_permission() {
    return current_user_can(CA_CAP) ? true : new WP_Error('ca_forbidden', 'Entra con una cuenta autorizada para gestionar averías.', ['status' => 403]);
}

function ca_page() {
    if (get_query_var('ca_sw')) {
        header('Content-Type: application/javascript; charset=utf-8');
        header('Service-Worker-Allowed: ' . wp_parse_url(home_url('/averias-campo/'), PHP_URL_PATH));
        header('Cache-Control: no-cache');
        $assets = plugin_dir_url(__FILE__) . 'app/';
        echo str_replace('__ASSETS__', wp_json_encode($assets, JSON_HEX_TAG | JSON_HEX_AMP), file_get_contents(__DIR__ . '/app/sw.js'));
        exit;
    }
    if (!get_query_var('ca_app') && !get_query_var('ca_session')) { return; }
    if (!defined('DONOTCACHEPAGE')) { define('DONOTCACHEPAGE', true); }
    nocache_headers();
    header('X-Content-Type-Options: nosniff');
    if (get_query_var('ca_session')) {
        // Cookie bootstrap is same-origin only, outside REST (which requires a nonce).
        header_remove('Access-Control-Allow-Origin');
        header_remove('Access-Control-Allow-Credentials');
        header('Cross-Origin-Resource-Policy: same-origin');
        wp_send_json(['authorized' => current_user_can(CA_CAP), 'nonce' => current_user_can(CA_CAP) ? wp_create_nonce('wp_rest') : null,
                     'login_url' => wp_login_url(home_url('/averias-campo/'))]);
    }
    header('Content-Type: text/html; charset=utf-8');
    header("Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: blob: https://tms-pnoa-ma.idee.es; connect-src 'self'; worker-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'");
    $html = file_get_contents(__DIR__ . '/app/index.html');
    $html = str_replace('<!-- ASSET_BASE -->', '<base href="' . esc_url(plugin_dir_url(__FILE__) . 'app/') . '">', $html);
    $html = str_replace('__API_BASE__', esc_url(rest_url(CA_NS . '/')), $html);
    $html = str_replace('__APP_HOME__', esc_url(home_url('/averias-campo/')), $html);
    $html = str_replace('href="#', 'href="' . esc_url(home_url('/averias-campo/')) . '#', $html);
    echo $html;
    exit;
}
add_action('template_redirect', 'ca_page', 0);

function ca_public($row) {
    $data = json_decode($row['public_data'], true);
    $coordinates = [$data['longitude'], $data['latitude']];
    unset($data['longitude'], $data['latitude']);
    $data['id'] = $row['id'];
    $data['status'] = $row['status'];
    $data['version'] = (int) $row['version'];
    foreach (['created_at', 'updated_at', 'closed_at'] as $key) {
        $data[$key] = $row[$key] ? str_replace(' ', 'T', $row[$key]) . 'Z' : null;
    }
    $data['photo_path'] = 'incidents/' . $row['id'] . '/photo';
    return ['type' => 'Feature', 'id' => $row['id'], 'geometry' => ['type' => 'Point', 'coordinates' => $coordinates], 'properties' => $data];
}

function ca_row($id, $photo = false) {
    global $wpdb;
    $columns = $photo ? 'photo' : 'id,public_data,status,version,created_at,updated_at,closed_at';
    return $wpdb->get_row($wpdb->prepare("SELECT $columns FROM {$wpdb->prefix}castrejon_incidents WHERE id=%s", $id), ARRAY_A);
}

function ca_list($request) {
    global $wpdb;
    $after = $request->get_param('after') ?? '';
    if ($after !== '' && !ca_uuid($after)) { return new WP_Error('ca_invalid', 'Cursor incorrecto.', ['status' => 422]); }
    $snapshot = $request->get_param('as_of') ?? gmdate('Y-m-d H:i:s');
    if (!is_string($snapshot) || !preg_match('/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/D', $snapshot) || $snapshot > gmdate('Y-m-d H:i:s')) {
        return new WP_Error('ca_invalid', 'Fecha de consulta incorrecta.', ['status' => 422]);
    }
    $rows = $wpdb->get_results($wpdb->prepare("SELECT id,public_data,status,version,created_at,updated_at,closed_at
      FROM {$wpdb->prefix}castrejon_incidents WHERE id > %s AND created_at <= %s ORDER BY id LIMIT 251", $after, $snapshot), ARRAY_A);
    if ($wpdb->last_error) { return new WP_Error('ca_storage', 'No se pudieron consultar las averías.', ['status' => 503]); }
    return new WP_REST_Response(['type' => 'FeatureCollection', 'coordinate_reference_system' => 'EPSG:4326',
      'features' => array_map('ca_public', array_slice($rows, 0, 250)), 'next' => count($rows) > 250 ? $rows[249]['id'] : null,
      'as_of' => $snapshot], 200, ['Cache-Control' => 'no-store']);
}

function ca_create($request) {
    global $wpdb;
    if (strlen($request->get_body()) > 3000000) { return new WP_Error('ca_size', 'La solicitud es demasiado grande.', ['status' => 413]); }
    try {
        $input = $request->get_json_params();
        $data = ca_validate($input);
        $photo = ca_photo($input['photo_base64'] ?? null);
    } catch (InvalidArgumentException $error) { return new WP_Error('ca_invalid', $error->getMessage(), ['status' => 422]); }
    $id = $data['id'];
    unset($data['id']);
    $fingerprint = hash('sha256', wp_json_encode($data) . $photo);
    $table = $wpdb->prefix . 'castrejon_incidents';
    $events = $wpdb->prefix . 'castrejon_incident_events';
    $now = current_time('mysql', true);
    $wpdb->query('START TRANSACTION');
    $result = $wpdb->query($wpdb->prepare("INSERT IGNORE INTO $table
      (id, public_data, photo, original_hash, status, version, created_at, updated_at, created_by)
      VALUES (%s,%s,%s,%s,'pendiente',1,%s,%s,%d)", $id, wp_json_encode($data), $photo, $fingerprint, $now, $now, get_current_user_id()));
    if ($result === false) { $wpdb->query('ROLLBACK'); return new WP_Error('ca_storage', 'No se pudo guardar; conserva el borrador y reintenta.', ['status' => 503]); }
    if ($result === 0) {
        $existing = $wpdb->get_var($wpdb->prepare("SELECT original_hash FROM $table WHERE id=%s", $id));
        $wpdb->query('ROLLBACK');
        if (!is_string($existing) || !hash_equals($existing, $fingerprint)) {
            return new WP_Error('ca_conflict', 'Este identificador ya tiene otros datos publicados. Comprueba la lista.', ['status' => 409]);
        }
        return new WP_REST_Response(ca_public(ca_row($id)), 200);
    }
    $audit = $wpdb->insert($events, ['incident_id' => $id, 'staff_id' => get_current_user_id(), 'status' => 'pendiente', 'version' => 1, 'changed_at' => $now]);
    if (!$audit) { $wpdb->query('ROLLBACK'); return new WP_Error('ca_storage', 'No se pudo completar el registro; reintenta.', ['status' => 503]); }
    $wpdb->query('COMMIT');
    return new WP_REST_Response(ca_public(ca_row($id)), 201);
}

function ca_update($request) {
    global $wpdb;
    $data = $request->get_json_params();
    if (!is_array($data) || count($data) !== 2 || !isset($data['status'], $data['version']) ||
        !in_array($data['status'], ['pendiente', 'en_reparacion', 'resuelta'], true) || !is_int($data['version']) || $data['version'] < 1) {
        return new WP_Error('ca_invalid', 'Estado o versión incorrectos.', ['status' => 422]);
    }
    $id = $request['id']; $now = current_time('mysql', true);
    $wpdb->query('START TRANSACTION');
    $changed = $wpdb->query($wpdb->prepare("UPDATE {$wpdb->prefix}castrejon_incidents SET status=%s, version=version+1, updated_at=%s,
      closed_at=CASE WHEN %s='resuelta' THEN COALESCE(closed_at,%s) ELSE NULL END WHERE id=%s AND version=%d",
      $data['status'], $now, $data['status'], $now, $id, $data['version']));
    if ($changed !== 1) { $wpdb->query('ROLLBACK'); return new WP_Error('ca_conflict', 'La avería cambió o no existe. Actualiza la lista antes de guardar.', ['status' => 409]); }
    if (!$wpdb->insert($wpdb->prefix . 'castrejon_incident_events', ['incident_id' => $id, 'staff_id' => get_current_user_id(), 'status' => $data['status'], 'version' => $data['version'] + 1, 'changed_at' => $now])) {
        $wpdb->query('ROLLBACK'); return new WP_Error('ca_storage', 'No se pudo guardar el cambio.', ['status' => 503]);
    }
    $wpdb->query('COMMIT');
    return ca_public(ca_row($id));
}

add_action('rest_api_init', function () {
    register_rest_route(CA_NS, '/incidents', [
      ['methods' => 'GET', 'callback' => 'ca_list', 'permission_callback' => '__return_true'],
      ['methods' => 'POST', 'callback' => 'ca_create', 'permission_callback' => 'ca_permission']
    ]);
    register_rest_route(CA_NS, '/incidents/(?P<id>[a-f0-9-]{36})', [
      'methods' => 'PATCH', 'callback' => 'ca_update', 'permission_callback' => 'ca_permission'
    ]);
    register_rest_route(CA_NS, '/incidents/(?P<id>[a-f0-9-]{36})/photo', [
      'methods' => 'GET', 'permission_callback' => '__return_true', 'callback' => function ($request) {
        $row = ca_row($request['id'], true);
        return $row ? new WP_REST_Response($row['photo'], 200, ['Content-Type' => 'image/jpeg', 'X-Content-Type-Options' => 'nosniff', 'Cache-Control' => 'public, max-age=3600'])
          : new WP_Error('ca_missing', 'Fotografía no encontrada.', ['status' => 404]);
      }
    ]);
});
add_filter('rest_pre_serve_request', function ($served, $result, $request) {
    if (str_starts_with($request->get_route(), '/' . CA_NS . '/incidents/') && $result->get_status() === 200 &&
        ($result->get_headers()['Content-Type'] ?? '') === 'image/jpeg') {
        echo $result->get_data(); return true;
    }
    return $served;
}, 10, 3);

add_action('admin_menu', function () {
    add_menu_page('Averías', 'Averías', CA_CAP, 'castrejon-averias', function () {
        echo '<div class="wrap"><h1>Averías · Castrejón</h1><p>Captura fotografías, ubicación y formulario. Las incidencias publicadas son visibles para cualquiera.</p><p><a class="button button-primary" href="' . esc_url(home_url('/averias-campo/')) . '">Abrir aplicación de campo</a></p><p>Para habilitar personal, asigna el rol «Operario de averías» en Usuarios. Los administradores ya tienen acceso. Este rol no permite editar el resto de la web.</p></div>';
    }, 'dashicons-location-alt', 30);
});
