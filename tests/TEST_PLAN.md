# План Unit Тестов для cachka

## Текущее покрытие
- ✅ Базовое кэширование async функций
- ✅ Базовое кэширование sync функций
- ❌ Все остальное не покрыто

---

## 1. Тесты для `TTLLRUCache` (`test_ttllrucache.py`)

### 1.1 Базовые операции
- [ ] `test_get_set` - получение и установка значений
- [ ] `test_get_missing_key` - получение несуществующего ключа (default value)
- [ ] `test_delete` - удаление ключа
- [ ] `test_contains` - проверка наличия ключа
- [ ] `test_len` - подсчет количества элементов

### 1.2 TTL (Time To Live)
- [ ] `test_ttl_expiration` - истечение TTL
- [ ] `test_ttl_not_expired` - значение не истекло
- [ ] `test_touch_extend_ttl` - продление TTL через touch()
- [ ] `test_touch_nonexistent_key` - touch() для несуществующего ключа

### 1.3 LRU Eviction
- [ ] `test_lru_eviction` - вытеснение по LRU при переполнении
- [ ] `test_lru_order_preserved` - сохранение порядка LRU
- [ ] `test_get_updates_lru` - get() обновляет позицию в LRU
- [ ] `test_set_updates_lru` - set() обновляет позицию в LRU

### 1.4 Шардирование
- [ ] `test_shard_distribution` - равномерное распределение по шардам
- [ ] `test_shard_isolation` - изоляция шардов (нет конфликтов)
- [ ] `test_consistent_shard_selection` - один ключ всегда попадает в один шард

### 1.5 Thread Safety
- [ ] `test_concurrent_get_set` - конкурентные get/set
- [ ] `test_concurrent_delete` - конкурентное удаление
- [ ] `test_race_condition_eviction` - гонки при eviction

### 1.6 Async API
- [ ] `test_get_async` - async версия get()
- [ ] `test_set_async` - async версия set()
- [ ] `test_delete_async` - async версия delete()
- [ ] `test_touch_async` - async версия touch()
- [ ] `test_get_or_set_async` - async версия get_or_set()

### 1.7 get_or_set
- [ ] `test_get_or_set_existing` - возврат существующего значения
- [ ] `test_get_or_set_new` - создание нового значения через factory
- [ ] `test_get_or_set_thread_safe` - потокобезопасность get_or_set

### 1.8 Cleanup
- [ ] `test_cleanup_expired` - очистка истекших записей
- [ ] `test_cleanup_returns_count` - возврат количества удаленных записей
- [ ] `test_background_cleanup` - фоновая очистка (start/stop)

### 1.9 Edge Cases
- [ ] `test_zero_maxsize_raises` - maxsize=0 вызывает ошибку
- [ ] `test_negative_ttl_raises` - отрицательный TTL вызывает ошибку
- [ ] `test_zero_shards_raises` - shards=0 вызывает ошибку
- [ ] `test_very_large_values` - очень большие значения
- [ ] `test_unicode_keys` - unicode ключи

### 1.10 Metrics (если включены)
- [ ] `test_metrics_hits` - подсчет hits
- [ ] `test_metrics_misses` - подсчет misses
- [ ] `test_metrics_evictions` - подсчет evictions

---

## 2. Тесты для `SQLiteStorage` (`test_storage.py`)

### 2.1 Базовые операции
- [ ] `test_get_set` - получение и установка значений
- [ ] `test_get_missing_key` - получение несуществующего ключа (None)
- [ ] `test_set_overwrite` - перезапись существующего ключа
- [ ] `test_concurrent_connections` - конкурентные подключения

### 2.2 TTL и истечение
- [ ] `test_ttl_expiration` - истечение TTL в БД
- [ ] `test_get_expired_returns_none` - получение истекшего ключа
- [ ] `test_cleanup_expired` - очистка истекших записей
- [ ] `test_cleanup_returns_count` - возврат количества удаленных

### 2.3 Шифрование
- [ ] `test_encryption_enabled` - шифрование работает
- [ ] `test_encryption_decryption` - зашифрованные данные расшифровываются
- [ ] `test_encryption_different_keys` - разные ключи дают разные шифры
- [ ] `test_encryption_without_key_raises` - ошибка при включенном шифровании без ключа
- [ ] `test_encryption_invalid_key_raises` - ошибка при неверном ключе
- [ ] `test_encryption_key_length` - проверка длины ключа (32 bytes)

### 2.4 Инициализация БД
- [ ] `test_db_initialization` - создание таблиц и индексов
- [ ] `test_wal_mode` - WAL режим включен
- [ ] `test_pragma_settings` - настройки PRAGMA применены

### 2.5 Edge Cases
- [ ] `test_very_large_values` - очень большие значения (BLOB)
- [ ] `test_special_characters_in_key` - специальные символы в ключах
- [ ] `test_empty_value` - пустое значение
- [ ] `test_close_connection` - закрытие соединения

### 2.6 Ошибки
- [ ] `test_invalid_db_path` - неверный путь к БД
- [ ] `test_corrupted_data` - поврежденные данные (decrypt error)

---

## 3. Тесты для `AsyncCache` (`test_async_cache_core.py`)

### 3.1 L1 Cache (Memory)
- [ ] `test_l1_hit` - попадание в L1 кэш
- [ ] `test_l1_miss_l2_hit` - промах L1, попадание L2
- [ ] `test_l1_miss_l2_miss` - промах обоих уровней
- [ ] `test_l2_promotes_to_l1` - L2 попадание промотирует в L1

### 3.2 Set Operations
- [ ] `test_set_updates_both_levels` - set() обновляет L1 и L2
- [ ] `test_set_with_ttl` - установка с TTL
- [ ] `test_set_overwrite` - перезапись существующего значения

### 3.3 Circuit Breaker
- [ ] `test_circuit_breaker_closed` - нормальная работа (CLOSED)
- [ ] `test_circuit_breaker_opens_on_failures` - открытие при ошибках
- [ ] `test_circuit_breaker_blocks_requests` - блокировка запросов в OPEN
- [ ] `test_circuit_breaker_recovery` - восстановление после таймаута
- [ ] `test_circuit_breaker_half_open` - переход в HALF_OPEN
- [ ] `test_circuit_breaker_resets_on_success` - сброс при успехе

### 3.4 Maintenance Loop
- [ ] `test_maintenance_loop_runs` - цикл очистки работает
- [ ] `test_maintenance_loop_cleanup` - очистка в цикле
- [ ] `test_maintenance_loop_stops_on_shutdown` - остановка при shutdown
- [ ] `test_no_maintenance_loop_when_disabled` - нет цикла при vacuum_interval=None

### 3.5 Health Check
- [ ] `test_health_check_healthy` - здоровый кэш
- [ ] `test_health_check_unhealthy` - нездоровый кэш
- [ ] `test_health_check_includes_metrics` - метрики в health check

### 3.6 Graceful Shutdown
- [ ] `test_graceful_shutdown` - корректное завершение
- [ ] `test_graceful_shutdown_stops_maintenance` - остановка maintenance loop
- [ ] `test_graceful_shutdown_closes_storage` - закрытие storage

### 3.7 Metrics (если включены)
- [ ] `test_metrics_l1_hit` - метрика L1 hit
- [ ] `test_metrics_l2_hit` - метрика L2 hit
- [ ] `test_metrics_miss` - метрика miss
- [ ] `test_metrics_errors` - метрика ошибок
- [ ] `test_metrics_duration` - метрика длительности операций
- [ ] `test_get_metrics_text` - получение текста метрик

### 3.8 Error Handling
- [ ] `test_get_handles_storage_error` - обработка ошибок storage
- [ ] `test_set_handles_storage_error` - обработка ошибок при set
- [ ] `test_pickle_error` - ошибка pickle при сериализации
- [ ] `test_unpickle_error` - ошибка unpickle при десериализации

### 3.9 Edge Cases
- [ ] `test_none_value` - кэширование None
- [ ] `test_complex_objects` - сложные объекты (dict, list, custom classes)
- [ ] `test_very_large_objects` - очень большие объекты

---

## 4. Тесты для `CacheRegistry` (`test_registry.py`)

### 4.1 Инициализация
- [ ] `test_initialize_default_config` - инициализация с дефолтной конфигурацией
- [ ] `test_initialize_custom_config` - инициализация с кастомной конфигурацией
- [ ] `test_initialize_twice_raises` - повторная инициализация вызывает ошибку
- [ ] `test_get_before_initialize_raises` - get() до инициализации вызывает ошибку

### 4.2 Singleton Behavior
- [ ] `test_singleton_instance` - один экземпляр на все вызовы
- [ ] `test_is_initialized` - проверка статуса инициализации

### 4.3 Shutdown
- [ ] `test_shutdown` - корректное завершение
- [ ] `test_shutdown_before_init` - shutdown до инициализации (не падает)
- [ ] `test_shutdown_closes_cache` - shutdown закрывает кэш

### 4.4 Thread Safety
- [ ] `test_concurrent_initialize` - конкурентная инициализация
- [ ] `test_concurrent_get` - конкурентный доступ к get()

---

## 5. Тесты для декоратора `@cached` (`test_decorator.py`)

### 5.1 Async Functions
- [ ] `test_async_function_caching` - кэширование async функций
- [ ] `test_async_function_cache_hit` - попадание в кэш
- [ ] `test_async_function_different_args` - разные аргументы = разные ключи
- [ ] `test_async_function_kwargs` - работа с kwargs
- [ ] `test_async_function_ttl` - соблюдение TTL

### 5.2 Sync Functions
- [ ] `test_sync_function_caching` - кэширование sync функций
- [ ] `test_sync_function_cache_hit` - попадание в кэш
- [ ] `test_sync_function_l1_cache` - использование L1 кэша
- [ ] `test_sync_function_without_event_loop` - работа без event loop

### 5.3 ignore_self
- [ ] `test_ignore_self_true` - игнорирование self в ключе
- [ ] `test_ignore_self_false` - включение self в ключ
- [ ] `test_ignore_self_class_method` - работа с методами класса

### 5.4 Function Metadata Preservation
- [ ] `test_preserves_function_name` - сохранение __name__
- [ ] `test_preserves_function_doc` - сохранение __doc__
- [ ] `test_preserves_function_annotations` - сохранение __annotations__ (для FastAPI)
- [ ] `test_preserves_function_signature` - сохранение сигнатуры

### 5.5 FastAPI Compatibility
- [ ] `test_fastapi_endpoint` - работа с FastAPI endpoint
- [ ] `test_fastapi_path_params` - path параметры
- [ ] `test_fastapi_query_params` - query параметры
- [ ] `test_fastapi_request_body` - request body

### 5.6 Edge Cases
- [ ] `test_decorator_with_no_args` - декоратор без аргументов
- [ ] `test_decorator_with_kwargs_only` - только kwargs
- [ ] `test_decorator_with_args_and_kwargs` - args и kwargs
- [ ] `test_decorator_nested_functions` - вложенные функции
- [ ] `test_decorator_recursive_function` - рекурсивные функции

### 5.7 Error Handling
- [ ] `test_decorator_cache_registry_not_initialized` - ошибка при неинициализированном registry
- [ ] `test_decorator_handles_cache_errors` - обработка ошибок кэша

---

## 6. Тесты для `make_cache_key` (`test_utils.py`)

### 6.1 Key Generation
- [ ] `test_key_generation_deterministic` - детерминированная генерация
- [ ] `test_key_different_for_different_args` - разные аргументы = разные ключи
- [ ] `test_key_same_for_same_args` - одинаковые аргументы = одинаковый ключ
- [ ] `test_key_handles_kwargs_order` - порядок kwargs не важен

### 6.2 Edge Cases
- [ ] `test_key_with_none` - ключ с None значениями
- [ ] `test_key_with_complex_objects` - сложные объекты в аргументах
- [ ] `test_key_with_unicode` - unicode в аргументах
- [ ] `test_key_length` - длина ключа (SHA256 = 64 hex chars)

---

## 7. Интеграционные тесты (`test_integration.py`)

### 7.1 End-to-End Scenarios
- [ ] `test_full_cache_flow` - полный цикл: set -> get -> expiration
- [ ] `test_l1_l2_interaction` - взаимодействие L1 и L2
- [ ] `test_concurrent_requests` - конкурентные запросы
- [ ] `test_cache_across_restarts` - кэш сохраняется между перезапусками (с БД)

### 7.2 Real-World Scenarios
- [ ] `test_api_endpoint_caching` - кэширование API endpoint
- [ ] `test_database_query_caching` - кэширование запросов к БД
- [ ] `test_expensive_computation_caching` - кэширование вычислений

### 7.3 Performance Tests
- [ ] `test_l1_performance` - производительность L1
- [ ] `test_l2_performance` - производительность L2
- [ ] `test_concurrent_performance` - производительность при конкурентности

---

## 8. Тесты для `CircuitBreaker` (`test_circuit_breaker.py`)

### 8.1 State Transitions
- [ ] `test_closed_to_open` - переход CLOSED -> OPEN
- [ ] `test_open_to_half_open` - переход OPEN -> HALF_OPEN
- [ ] `test_half_open_to_closed` - переход HALF_OPEN -> CLOSED
- [ ] `test_half_open_to_open` - переход HALF_OPEN -> OPEN при ошибке

### 8.2 Threshold Logic
- [ ] `test_threshold_counting` - подсчет ошибок до threshold
- [ ] `test_threshold_reset` - сброс счетчика при успехе
- [ ] `test_recovery_timeout` - таймаут восстановления

### 8.3 Thread Safety
- [ ] `test_concurrent_failures` - конкурентные ошибки
- [ ] `test_concurrent_successes` - конкурентные успехи

---

## 9. Тесты для `CacheConfig` (`test_config.py`)

### 9.1 Validation
- [ ] `test_default_config` - дефолтная конфигурация
- [ ] `test_custom_config` - кастомная конфигурация
- [ ] `test_config_validation` - валидация полей (Pydantic)
- [ ] `test_invalid_config_raises` - неверная конфигурация вызывает ошибку

### 9.2 Optional Features
- [ ] `test_config_with_encryption` - конфигурация с шифрованием
- [ ] `test_config_with_metrics` - конфигурация с метриками
- [ ] `test_config_with_tracing` - конфигурация с трейсингом

---

## Приоритеты

### Высокий приоритет (критично для работы)
1. TTLLRUCache: базовые операции, TTL, LRU eviction
2. SQLiteStorage: базовые операции, TTL, шифрование
3. AsyncCache: L1/L2 взаимодействие, circuit breaker
4. Декоратор: async/sync функции, ignore_self, метаданные

### Средний приоритет (важно для качества)
5. CacheRegistry: инициализация, shutdown
6. CircuitBreaker: все состояния
7. Интеграционные тесты: основные сценарии

### Низкий приоритет (nice to have)
8. Performance тесты
9. Edge cases
10. Metrics тесты (если не критично)

---

## Рекомендации по реализации

1. Использовать `pytest` и `pytest-asyncio`
2. Использовать фикстуры для создания тестовых экземпляров
3. Использовать временные файлы для БД (`:memory:` или `tempfile`)
4. Мокировать внешние зависимости (Prometheus, OpenTelemetry)
5. Использовать `freezegun` или `time.time` моки для TTL тестов
6. Параметризовать тесты где возможно (`@pytest.mark.parametrize`)

