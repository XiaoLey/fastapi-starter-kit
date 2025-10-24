DROP TRIGGER IF EXISTS tgr_update_updated_at_column ON users;
                CREATE TRIGGER tgr_update_updated_at_column
                BEFORE UPDATE ON users
                FOR EACH ROW
                EXECUTE FUNCTION update_updated_at_column();